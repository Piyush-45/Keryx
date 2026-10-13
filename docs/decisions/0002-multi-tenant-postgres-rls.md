# 0002 — Multi-tenancy with a shared Postgres and row-level security

- **Date:** 2026-10-13
- **Status:** accepted

## Context
Every company (tenant) must be isolated, onboarding must need no code, and a solo builder must be
able to operate it. Options: database per tenant, schema per tenant, or shared tables with `org_id`.

## Decision
Shared tables with `org_id` on every tenant-owned row, enforced by Postgres row-level security using
a per-request/per-job `app.current_org` setting. Agents are config (versioned JSON), not code.

## Alternatives considered
- Database per tenant — strongest isolation, heavy ops and migrations for a solo builder.
- Schema per tenant — migration fan-out grows with tenants.

## Consequences
- One migration path, cheap onboarding.
- Every new table needs `org_id`, an RLS policy, and an isolation test.
- If an enterprise later demands physical isolation, offer a dedicated deployment rather than redesigning.
