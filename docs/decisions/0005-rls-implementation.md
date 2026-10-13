# 0005 — Row-level security: how tenant isolation is implemented

- **Date:** 2026-10-13
- **Status:** accepted
- **Builds on:** 0002 (shared Postgres, `org_id` + RLS)

## Context
0002 chose RLS. This records the mechanics, because each detail closes a specific hole: roles that
bypass RLS, settings that leak across pooled connections, cross-tenant foreign keys, and code paths
that run before the org is known (inbound calls, third-party webhooks, schedulers).

## Decision

### Roles
| Role | Login | Attributes | Purpose |
| --- | --- | --- | --- |
| `vp_migrator` | yes | owns databases and tables; not superuser | Alembic only |
| `vp_app` | yes | **not superuser, not owner, NOBYPASSRLS**, DML via default privileges, no DDL, no access to `alembic_version` | API and all workers |
| `vp_resolver` | **no** | BYPASSRLS; owns only the resolver functions below; `SELECT` on exactly the columns they read | added with the first resolver |

Roles are provisioned outside migrations (`scripts/db/init.sql`; secrets manager in real envs).
Creating a BYPASSRLS role needs a superuser, which migrations never run as.

### Scoping
- One function decides the current tenant: `app_current_org()` =
  `NULLIF(current_setting('app.current_org', true), '')::uuid`. The NULLIF matters: once a
  session has used the setting, it reads as `''` (not NULL) after the transaction ends.
- `vp_db.session.tenant_session(org_id)` runs `set_config('app.current_org', org, true)` at the start
  of **every** transaction in the session (SQLAlchemy `after_begin`). `true` = transaction-local, so
  the value never reaches the next user of a pooled connection (PgBouncer transaction mode safe),
  and a mid-block commit doesn't drop the scope.
- No org set → policies match nothing → reads are empty and writes fail (fail closed).
- App code has no unscoped session. Code that runs before the org is known uses a resolver (below).

### Tables
- Every tenant table: `org_id uuid NOT NULL REFERENCES organizations ON DELETE RESTRICT`,
  `UNIQUE (org_id, id)`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy
  `tenant_isolation FOR ALL USING (org_id = app_current_org()) WITH CHECK (same)`.
  Migrations call `vp_db.rls.enable_tenant_rls(table)`.
- FKs between tenant tables are **composite** `(org_id, x_id) → parent (org_id, id)`. RLS only checks
  the row being written, so a single-column FK would let org A's row point at org B's row.
- `organizations`: visible only to itself (`id = app_current_org()`). Creating an org = generate the
  id in the app, scope to it, insert. Org deletion is an explicit offboarding job (RESTRICT FKs).
- `users`: global identity, no `org_id`. Readable when a membership in the current org exists;
  insertable from any tenant context; no UPDATE/DELETE policy until auth (Phase 3) decides
  self-service profile edits. Pre-org lookups (login by email) are designed with auth.
- `region`: `in` | `us` | `eu`, default `in`.

### Resolvers: entering a tenant from an unscoped request
Some requests carry no org: **inbound calls** (telephony webhook knows only the dialed number),
**third-party webhooks** (CRM, calendar, payment-link providers), and **schedulers** that iterate
orgs. Pattern:

1. Authenticate the request first with platform-level credentials (e.g. Plivo/Twilio request
   signature with our account token). Reject before touching tenant data.
2. Call a **narrow resolver function** that maps one opaque key to an `org_id` and nothing else:
   - `resolve_inbound_number(e164 text) RETURNS uuid` — dialed number → owning org (NULL if
     unassigned/inactive).
   - `resolve_webhook_endpoint(token text) RETURNS uuid` — per-integration webhook URL token → org.
   - `list_active_org_ids() RETURNS SETOF uuid` — for the campaign scheduler (decision of
     2026-10-13; ids only).
3. Open a normal `tenant_session(org_id)` and do everything else under RLS (load the number's agent
   version, verify tenant-level webhook secrets, write events).

Resolver rules:
- `SECURITY DEFINER`, owned by `vp_resolver` (BYPASSRLS, NOLOGIN). Not owned by `vp_migrator`:
  FORCE RLS applies to the table owner too, so an owner-defined function would see nothing.
- `SET search_path = pg_catalog, public` (prevents search-path hijacking), `STABLE`, `STRICT`.
- Returns only ids. Never rows, names or config.
- `REVOKE EXECUTE ... FROM PUBLIC; GRANT EXECUTE ... TO vp_app`.
- One resolver per entry point, each added in the migration that needs it, each with a test that it
  returns only the id and that `vp_app` cannot read the underlying table directly.

### Phone numbers are globally unique
`phone_numbers.e164` has a **global** `UNIQUE (e164)`, not `(org_id, e164)`. A dialed number must
resolve to exactly one org. Moving a number between orgs = release from one, then attach to the
other.

### Tests (required for every new tenant table)
- Isolation tests in `api/tests/tenancy/` run as `vp_app` through `tenant_session`.
- Catalog guards fail the build if any table lacks ENABLE+FORCE+policy, if an `org_id` table lacks
  the standard policy or `UNIQUE (org_id, id)`, or if `vp_app` gains superuser/BYPASSRLS/ownership.

## Alternatives considered
- Per-request `SET` (session-level) — leaks across pooled connections.
- App-level `WHERE org_id = ...` only — one missed filter leaks data; RLS is the backstop.
- A BYPASSRLS service role for webhooks/schedulers — any bug in that code path reads every tenant.
  Resolvers limit the unscoped surface to "key → id".
- Owner-owned SECURITY DEFINER functions — blocked by FORCE RLS (and dropping FORCE weakens all tables).

## Consequences
- Every tenant table costs: `org_id`, composite FKs, one helper call, isolation tests.
- Cross-tenant analytics for the platform (e.g. usage totals) need their own resolver-style
  functions or a separate reporting path; never the app role.
- Bulk/backfill migrations that touch tenant rows must set `app.current_org` per org.
