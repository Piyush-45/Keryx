# 0006 — Provider registry, presets pinned at publish, fallback chains

- **Date:** 2026-10-14
- **Status:** accepted

## Context
STT/LLM/TTS vendors must be swappable per tenant without pipeline changes (0001), every provider
needs a fallback, Indian languages need Sarvam alongside global vendors, and published agent versions
are immutable. Pipecat already wraps each vendor as a service; we need one controlled place that
picks, keys and orders them.

## Decision
- **Split by dependency.**
  - `vp_shared.providers` (no Pipecat; API + workers): spec parsing (`vendor[:model]`,
    `vendor:voice` for TTS), vendors per kind (tested against the agent config schema), metering
    unit per kind (STT audio-seconds, LLM tokens, TTS characters), presets, `resolve_voice()`.
  - `workers/voice/worker/providers/` (Pipecat): `ProviderRegistry`, `ProviderChain`,
    `CredentialResolver`, and one adapter module per vendor+kind. Adapter modules are the only code
    allowed to import vendor services; a test (AST scan) enforces it.
- **Presets are resolved at publish.** `resolve_voice(config.voice)` turns preset + per-kind overrides
  into explicit primary/fallback specs. The result (`ResolvedVoice.to_json()`) is stored on the agent
  version (`agent_versions.resolved_voice`), and workers build from that, never from the preset name.
  Editing a preset changes only versions published afterwards.
- **Fallback chains.** A chain is `primary, *fallback` (fallback vendors differ from the primary's).
  - Phase 1, start of call: `build_first()` walks the chain until a provider builds (missing key,
    adapter error, unknown vendor → next). Each skip is a `FallbackRecord`, emitted as a
    `provider.fallback` event with `reason: startup`.
  - Phase 1, LLM per request: the pipeline factory calls `build_next(after, "error" | "latency", …)`
    when an LLM request fails or breaches its latency budget, and retries that request on the next
    provider. (The Pipecat processor that does this is part of the pipeline factory.)
  - Phase 5: STT/TTS switching mid-call (stream handover), and latency-triggered switching for them.
- **Credentials.** `CredentialResolver.api_key(org_id, vendor)`. Now: platform keys from env
  (`EnvCredentialResolver`). Phase 3: a BYOK resolver reads the tenant's encrypted integration and
  falls back to platform keys per tenant policy. Adapters never read env or the DB themselves.
- **Cost.** Adapters/services report units only (in `call.ended` usage). Prices live in a separate
  table with effective dates (Phase 3 metering), so price changes never touch adapter code.
- **Construction is offline.** Adapter factories must not do network I/O; connections start with the
  pipeline. Tests build every adapter with a dummy key and check model, voice, language and
  temperature reach the service.

## Alternatives considered
- Store the preset name on the agent version and resolve at call start — preset edits would silently
  change published agents; breaks immutability.
- Versioned preset names (`india-standard@2`) — works, but every edit needs a new name and migration
  of defaults; resolving at publish gives the same guarantee with less ceremony.
- Pipecat's service switcher for everything now — mid-call STT/TTS switching needs stream handover
  and is Phase 5 work; LLM requests are naturally retryable per request.
- Calling vendor SDKs directly — loses Pipecat's frame handling and metrics; more code per vendor.

## Consequences
- Adding a vendor = one adapter module + catalog entry + schema enum + tests.
- `pipecat-ai` sits in the shared uv lockfile (0003): it currently pins `websockets` to 16.x for the
  whole workspace. If that conflicts with API needs, split the voice worker into its own workspace.
- Adapter tests read Pipecat's private `_settings`; a Pipecat upgrade may need test updates.
- Preset contents (model/voice ids) are data and must be re-verified against vendor catalogs before
  production.
