# 0003 — Monorepo with a uv workspace and a pnpm workspace

- **Date:** 2026-10-13
- **Status:** accepted

## Context
The repo holds one API, three Python worker types, a Next.js dashboard and shared schemas used by
both Python and TypeScript. A solo builder needs one command to lint/test everything and one place
to pin dependency versions.

## Decision
A single repo. Python packages are members of one **uv workspace** (root `pyproject.toml`, one
`uv.lock`, shared ruff/mypy/pytest config). JS packages are members of one **pnpm workspace**
(`dashboard`, `packages/shared/ts`). Python 3.12 and Node 22 LTS are pinned.

## Alternatives considered
- Separate repos per service — version skew of shared schemas, more CI to maintain.
- Poetry / pip-tools — slower, no first-class workspaces.
- Turborepo / Nx — not needed at two JS packages; revisit if the JS side grows.

## Consequences
- `uv run pytest` and `pnpm test` from the root cover everything.
- All Python services share one lockfile; a heavy dependency in one worker (e.g. Pipecat) is resolved
  for all. If that causes conflicts, split the voice worker into its own workspace.
- Local Postgres/Redis come from `docker-compose.yml`.
