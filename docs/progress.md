# Progress

Update at the end of every session. Newest entries at the top of "Log".

## Current
- **Phase:** 0 — System design
- **Focus now:** provider registry + call event model plan (awaiting approval)
- **Next up:** implement registry + events, then Phase 1 pipeline factory

## Open questions (decide before they block)
- [ ] India-first or global-first? (first CRM, default telephony, compliance depth)
- [ ] Launch industry 1 (and maybe 2)?
- [ ] Cloud provider + region for workers (Mumbai if India-first)
- [ ] Design partners: who are the first 3 prospects?

## Blockers
- No git remote yet; CI workflow is written and verified locally but has never run on GitHub.

## Log
- 2026-10-13 — Tenant model + RLS built: new `packages/db` (`vp_db`: models, `tenant_session`, RLS helpers); migration 0001 (organizations, users, memberships; ENABLE+FORCE RLS; `app_current_org()`); 18 isolation/guard tests against `vp_test` as `vp_app` (mutation-checked: removing FORCE, session-level scoping, or a permissive policy each fail the suite); Postgres service in CI. Found and fixed a `tenant_session` bug (commit mid-block broke the session). ADR 0005 accepted incl. resolver pattern for inbound calls/webhooks (design only) and globally unique `phone_numbers.e164`.
- 2026-10-13 — Agent config schema v1 finalized (recording required, fallback vendor ≠ primary, codegen-friendly tools). Single validator exposed as `POST /agent-configs/validate`; dashboard uses it via `lib/api/agent-config.ts`. Codegen (Pydantic + zod, `@vp/shared`) with CI drift check. ADR 0004 accepted. Local DB without Docker: brew postgresql@16 + redis, `vp_dev`/`vp_test`, roles `vp_migrator` (owner, Alembic) and `vp_app` (non-superuser, NOBYPASSRLS, DML only), TCP password auth; docs/local-setup.md. Docker compose kept as optional (untested: Docker not installed).
- 2026-10-13 — git init. Repo scaffold: uv workspace (api, 3 workers, vp_shared) + pnpm workspace (dashboard on Next 16 / Tailwind 4 / shadcn / Vitest), Makefile check targets, CI (ruff, mypy strict, pytest, pnpm lint/typecheck/test, gitleaks), pre-commit. Agent config JSON Schema v1 **draft** in packages/shared with validator, examples and tests. ADR 0003 (monorepo tooling, accepted), 0004 (schema versioning, proposed). Codegen and `packages/shared/ts` deferred until schema review.
- 2026-10-13 — Product research, roadmap and architecture draft done. Repo docs created (CLAUDE.md, architecture, roadmap, progress, decisions 0001–0002).
