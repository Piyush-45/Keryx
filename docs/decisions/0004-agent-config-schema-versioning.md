# 0004 — Agent config: JSON Schema as source of truth, integer schema versions

- **Date:** 2026-10-13
- **Status:** proposed

## Context
Agent behaviour is config, not code (0002). The same config is written by the dashboard (TS),
stored and published by the API (Python), and executed by voice workers (Python). Published
`agent_versions` rows are immutable and calls pin them, so configs written today must still load
after the format evolves.

## Decision
- `packages/shared/agent_config.schema.json` (JSON Schema 2020-12) is authoritative. Pydantic
  models and zod schemas are **generated** from it, never hand-written; CI fails on drift.
- Every config carries `schema_version` (an integer string, currently `"1"`). Workers reject unknown
  versions. A breaking change adds a new schema version plus a migration function
  `vN → vN+1`; old published versions are upgraded on load, never rewritten in the database.
  Additive optional fields do not bump the version.
- Shape is validated by the schema; cross-references (flow states, tool names, `{variables}`) by
  `vp_shared.agent_config.validate_agent_config`. The API runs both before publishing.
- `additionalProperties: false` everywhere, so typos fail at publish time, not mid-call.
- Secrets never appear in config: tools reference an `integration_id`, whose credentials are
  encrypted at rest. There is no payment/card tool type.

## Alternatives considered
- Pydantic models as source, exporting JSON Schema — Python-centric; TS side would depend on a
  Python build step and on Pydantic's schema output quirks.
- zod as source — same problem in reverse.
- Semver schema versions — more ceremony than needed; additive changes don't need a version.

## Consequences
- One file to review for any change to agent capabilities.
- Codegen step to maintain (datamodel-code-generator, json-schema-to-zod).
- Cross-reference rules live in code and must be mirrored in the dashboard editor (or the dashboard
  calls the API's validate endpoint).
