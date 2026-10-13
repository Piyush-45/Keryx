# Voice Agent Platform

Multi-tenant voice agent platform: companies create AI phone agents that do real work on calls
(book, qualify, verify, update CRM), run outbound campaigns from CSV/Excel, and get structured
data back from every call. Voice quality is table stakes; outcomes and data are the product.

## Source of truth (read these before planning any task)
- @docs/progress.md — current phase, what's done, what's next, open questions
- @docs/architecture.md — components, call lifecycle, data model, provider registry, events
- docs/roadmap.md — phases with checkboxes (read when picking or finishing a task)
- docs/decisions/ — one file per architectural decision; read the relevant one before changing that area

## Stack
- Voice workers: Python 3.12, Pipecat (cascaded STT → LLM → TTS), Pipecat Flows for call states
- API: FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2
- Dashboard: Next.js (App Router, TypeScript), Tailwind, shadcn/ui
- Data: Postgres (row-level security per tenant), Redis (queues + rate limits), S3-compatible storage (recordings)
- Telephony: Plivo (India), Twilio (global)
- Providers: STT Deepgram / Sarvam · LLM OpenAI / Gemini / Claude · TTS Cartesia / ElevenLabs / Sarvam

## Repo layout
- `api/` — FastAPI control plane (tenants, agents, campaigns, calls, integrations, webhooks)
- `workers/voice/` — Pipecat call workers (build pipeline from agent config at call start)
- `workers/postcall/` — post-call jobs (transcript, extraction, dispositions, CRM write-back, webhooks)
- `workers/campaigns/` — campaign scheduler (windows, concurrency, retries)
- `dashboard/` — Next.js app
- `packages/shared/` — shared schemas (agent config JSON schema, event types)
- `docs/` — architecture, roadmap, progress, decisions

## Commands
<!-- Fill in during Phase 0 scaffolding, then keep current. -->
- API dev: `cd api && uv run fastapi dev`
- Voice worker: `cd workers/voice && uv run python -m worker`
- Dashboard: `cd dashboard && pnpm dev`
- Tests: `uv run pytest` (Python) · `pnpm test` (dashboard)
- Migrations: `cd api && uv run alembic upgrade head`

## Non-negotiable rules
- **Tenant isolation:** every tenant-owned table has `org_id`; every query goes through the
  tenant-scoped session (Postgres RLS). Never write a query that can return another org's rows.
- **Config-driven agents:** no per-company code. Agent behaviour lives in versioned agent config
  JSON (`packages/shared/agent_config.schema.json`). Workers build the pipeline from it.
- **Providers via the registry only:** STT/LLM/TTS are created through `ProviderRegistry`;
  never import a vendor SDK directly in pipeline code. Every provider has a fallback.
- **Events are the backbone:** emit `call.started`, `turn`, `tool_call`, `transfer`, `call.ended`,
  `extraction.done`. Analytics, webhooks and the call detail page read events, not ad-hoc logs.
- **Measure latency from day one:** log per-turn timings (STT final → LLM first token → TTS first
  audio). Target: median voice-to-voice < 1s.
- **No card data in the pipeline:** payments only via payment links. Never capture card digits.
- **Secrets:** env vars / secrets manager only. Never commit keys. Tenant BYOK keys are encrypted at rest.
- **India outbound compliance:** campaigns must respect calling windows, DND scrub status,
  consent flag, and number series (140 promotional / 160 transactional).

## Code conventions
- Python: type hints everywhere, ruff + mypy clean, async I/O, small modules.
- TypeScript: strict mode, server components by default, zod for API response parsing.
- Tests: every bug fix adds a test; tenant-isolation tests for every new table.
- Migrations: one Alembic migration per schema change, never edit a merged migration.

## How to work (every session)
1. Read docs/progress.md, then propose a short plan before writing code. Wait for approval on anything touching schema, tenancy or providers.
2. Work in small steps; run tests; commit with clear messages.
3. Big decision? Add `docs/decisions/NNNN-title.md` (use `_template.md`).
4. End of session: update docs/progress.md (done / next / blockers) and tick docs/roadmap.md.
