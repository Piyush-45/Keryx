# Architecture

Status: draft (Phase 0). Update this file when the design changes; record the reason in docs/decisions/.

## 1. Big picture

Three planes, connected by Postgres and an event stream:

```mermaid
flowchart LR
  subgraph Control["Control plane"]
    D[Next.js dashboard] --> A[FastAPI API]
    A --> PG[(Postgres + RLS)]
  end
  subgraph Data["Data plane (real time)"]
    T[Plivo / Twilio / WebRTC] --> W[Pipecat voice worker]
    W --> R[Provider registry<br/>STT · LLM · TTS]
    W -- tools over HTTP --> X[Tenant APIs / calendar / CRM]
  end
  subgraph Post["Post-call plane (async)"]
    Q[Redis queue] --> P[Post-call worker]
    P --> S[(Object storage<br/>recordings)]
    P --> I[Integrations + webhooks]
  end
  PG -. agent config at call start .-> W
  W -- events --> Q
  P --> PG
  C[Campaign scheduler] --> T
  PG -.-> C
```

- **Control plane** stores tenants, agents (versioned config), numbers, campaigns, calls, results.
- **Data plane** handles live audio. A worker loads the agent config for the dialed/dialing number and
  builds a Pipecat pipeline at call start. No tenant-specific code exists.
- **Post-call plane** turns a finished call into data: recording, transcript, summary, extractions,
  dispositions, CRM write-back, outbound webhooks.

## 2. Call lifecycle

1. **Inbound:** telephony webhook → API resolves `phone_number → agent_version` → assigns a worker →
   worker connects media stream.
   **Outbound:** campaign scheduler picks the next eligible contact (window, concurrency, retries,
   compliance) → places call via telephony API → same worker path on answer.
2. Worker builds pipeline from config: VAD/turn detection → STT → LLM (+ tools, Flows state) → TTS.
3. During the call: emit `turn` and `tool_call` events with timings; filler lines for slow tools.
4. Optional `transfer` to a human number.
5. `call.ended` → queue post-call job.
6. Post-call worker: store recording → final transcript → summary → extractions + dispositions
   (with confidence) → low-confidence items to review queue → CRM write-back → signed webhook →
   `extraction.done`.

## 3. Multi-tenancy

- Tenant = `organization`. Every tenant-owned row has `org_id`.
- Postgres row-level security keyed on `app.current_org` set per request/job.
- API auth resolves user → membership → org; workers act with the org of the call.
- Per-tenant settings: provider presets, BYOK keys (encrypted), retention days, PII redaction, calling windows.

## 4. Data model (first cut)

| Table | Key columns | Notes |
| --- | --- | --- |
| organizations | id, name, region, settings_json | tenant root |
| users / memberships | user_id, org_id, role | owner, admin, member |
| agents | id, org_id, name, industry_template | logical agent |
| agent_versions | id, agent_id, version, config_json, published_at | immutable; calls pin a version |
| phone_numbers | id, org_id, e164, provider, series, agent_id | 140/160 series stored |
| contacts | id, org_id, e164, attributes_json, consent, dnd_status | dedupe on (org_id, e164) |
| campaigns | id, org_id, agent_version_id, schedule_json, retry_json, concurrency, status | |
| campaign_contacts | campaign_id, contact_id, row_vars_json, attempts, state, last_outcome | one row per CSV row |
| calls | id, org_id, agent_version_id, campaign_id?, contact_id?, direction, status, started_at, ended_at, cost_json | |
| call_events | id, call_id, type, ts, payload_json | turn, tool_call, transfer, latency timings |
| extraction_fields | id, org_id, agent_id, name, type, question, options, regex | typed definitions |
| call_results | call_id, field_id, value, confidence, reasoning, reviewed_by? | extractions + dispositions |
| integrations | id, org_id, kind, credentials_enc, settings_json | calendar, CRM, n8n |
| webhooks | id, org_id, url, secret, events | signed, retried |
| usage_records | org_id, call_id, minutes, provider_costs_json | metering before billing |

## 5. Agent config (shape)

```json
{
  "language": ["hi-IN", "en-IN"],
  "persona": { "name": "Asha", "prompt": "..." },
  "greeting": "Namaste {name}, ...",
  "flow": { "states": [ { "id": "verify", "next": ["book", "transfer"] } ] },
  "voice": { "preset": "india-standard", "stt": "sarvam", "llm": "gpt", "tts": "sarvam:voice-id" },
  "tools": [ { "name": "check_slots", "type": "calendar", "integration_id": "..." } ],
  "extraction_fields": ["field_id_1", "field_id_2"],
  "transfer": { "number": "+91...", "when": "caller asks for a human" },
  "limits": { "max_call_seconds": 600, "silence_timeout_s": 8 }
}
```

The JSON Schema in `packages/shared/` is authoritative; this is illustrative.

## 6. Provider registry

```python
class STT(Protocol): ...
class LLM(Protocol): ...
class TTS(Protocol): ...

registry.build(kind="tts", spec="cartesia:voice-id", org=org)  # resolves keys (platform or BYOK)
```

- One adapter per vendor, one file each.
- Fallback order per kind (e.g. TTS: preset → secondary) triggered on error or latency breach.
- Each adapter reports cost units so `usage_records` can price every call.

## 7. Latency budget (targets, to be measured)

| Stage | Target |
| --- | --- |
| End-of-turn detection | ≤ 250 ms |
| STT final transcript | ≤ 150 ms after end of turn |
| LLM first token | ≤ 400 ms |
| TTS first audio | ≤ 150 ms |
| **Voice-to-voice (median)** | **< 1 s** |

Host workers in the same region as callers and providers (Mumbai for India).

## 8. Campaign scheduler

- Eligibility: calling window (contact's timezone), consent, DND status, attempts < max, retry gap elapsed.
- Concurrency cap per campaign and per org; respects telephony account limits.
- Outcomes: answered, no-answer, busy, failed, voicemail → retry rules.
- Inbound callback from a campaign contact is matched to its `campaign_contacts` row.

## 9. Open questions

- India-first vs global-first (decides first CRM, default telephony, compliance depth).
- Launch industries (decides templates and extraction defaults).
- Hosting: single cloud region at start; which provider.
