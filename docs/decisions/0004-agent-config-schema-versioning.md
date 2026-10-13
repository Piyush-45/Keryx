# 0004 — Agent config: JSON Schema as source of truth, one validator, integer schema versions

- **Date:** 2026-10-13
- **Status:** accepted

## Context
Agent behaviour is config, not code (0002). The same config is written by the dashboard (TS),
stored and published by the API (Python), and executed by voice workers (Python). Published
`agent_versions` rows are immutable and calls pin them, so configs written today must still load
after the format evolves.

## Decision
- `packages/shared/agent_config.schema.json` (JSON Schema 2020-12) is authoritative.
- **One validator:** `vp_shared.agent_config.validate_agent_config` = JSON Schema + rules the schema
  cannot express (flow state refs, tool refs, declared `{variables}`, fallback vendor ≠ primary
  vendor). It returns `{path, message}` errors.
  - The API runs it before publishing and exposes it as `POST /agent-configs/validate`.
  - The dashboard validates **only** through that endpoint. No TypeScript reimplementation.
  - Workers load configs with `parse_agent_config` (validate, then build the typed model).
- **Codegen, never hand-written models:** `make codegen` produces Pydantic v2 models
  (datamodel-code-generator, options in root `pyproject.toml`) and zod schemas
  (json-schema-to-zod after `$ref` dereferencing, `packages/shared/ts/scripts/codegen.mjs`).
  CI (`make codegen-check`) fails if committed output is stale. Generated models give types and
  parsing; they are not the validator (they don't enforce cross-references or conditionals).
- **Codegen-friendly schema style:** flat objects with `additionalProperties: false` (no
  `allOf` + `unevaluatedProperties`); discriminated unions as `anyOf` on a `type` const.
- **Versioning:** every config carries `schema_version` (integer string, currently `"1"`). Workers
  reject unknown versions. A breaking change adds a new version plus a migration `vN → vN+1`; old
  published versions are upgraded on load, never rewritten in the database. Additive optional
  fields do not bump the version.
- **Explicit over implicit:** `recording` is required (`enabled` plus a disclosure line when
  enabled). Every explicit provider has ≥ 1 fallback from a different vendor.
- **No secrets in config:** tools reference an `integration_id` (credentials encrypted at rest).
  There is no payment/card tool type.

## Alternatives considered
- Pydantic models as source, exporting JSON Schema — Python-centric; TS would depend on a Python
  build step and Pydantic's schema quirks.
- zod as source — same problem in reverse.
- Validating in the dashboard with generated zod/ajv — two validators drift; cross-reference rules
  would need a TS copy.
- Semver schema versions — more ceremony than needed.

## Consequences
- One file to review for any change to agent capabilities; one function decides validity.
- Dashboard config editing needs the API running (fine: it needs it for everything else).
- The zod codegen drops the voice "preset or all of stt/llm/tts" rule, because json-schema-to-zod
  would erase the `voice` type. The API still enforces it.
