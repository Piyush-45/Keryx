# Progress

Update at the end of every session. Newest entries at the top of "Log".

## Current
- **Phase:** 0 — System design
- **Focus now:** review agent config schema v1 draft (ADR 0004 proposed) → codegen (Pydantic + zod) → tenant model
- **Next up:** tenant model + RLS (needs approval), provider registry interface, call event model

## Open questions (decide before they block)
- [ ] India-first or global-first? (first CRM, default telephony, compliance depth)
- [ ] Launch industry 1 (and maybe 2)?
- [ ] Cloud provider + region for workers (Mumbai if India-first)
- [ ] Design partners: who are the first 3 prospects?

## Blockers
- No git remote yet; CI workflow is written and verified locally but has never run on GitHub.
- Docker isn't installed locally; `docker-compose.yml` (Postgres/Redis) is untested.

## Log
- 2026-10-13 — git init. Repo scaffold: uv workspace (api, 3 workers, vp_shared) + pnpm workspace (dashboard on Next 16 / Tailwind 4 / shadcn / Vitest), Makefile check targets, CI (ruff, mypy strict, pytest, pnpm lint/typecheck/test, gitleaks), pre-commit. Agent config JSON Schema v1 **draft** in packages/shared with validator, examples and tests. ADR 0003 (monorepo tooling, accepted), 0004 (schema versioning, proposed). Codegen and `packages/shared/ts` deferred until schema review.
- 2026-10-13 — Product research, roadmap and architecture draft done. Repo docs created (CLAUDE.md, architecture, roadmap, progress, decisions 0001–0002).
