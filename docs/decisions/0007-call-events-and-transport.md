# 0007 — Call events: typed schema, Redis Streams transport, Postgres store

- **Date:** 2026-10-14
- **Status:** accepted

## Context
Events are the backbone (CLAUDE.md): the call detail page, analytics, webhooks and latency tracking
all read them. They are produced inside the real-time audio path, where nothing may block, and must
end up durable, tenant-isolated and ordered per call. Transcripts are PII; card numbers must never
be stored.

## Decision
- **Schema.** `packages/shared/events.schema.json` is authoritative, with the same codegen + drift
  check as the agent config (0004). Envelope `{id, type, v, org_id, call_id, seq, ts, payload}`;
  types: `call.started`, `turn`, `tool_call`, `transfer`, `provider.fallback`, `call.ended`,
  `extraction.done`. `vp_shared.events.validate_event` = per-type schema + rules the schema can't
  express. Producers validate on emit; the consumer validates again.
- **Turns.** One `turn` per exchange. `user` and `agent` are each an object or null: `user` is null
  for the greeting or agent-initiated speech, `agent` is null when the caller speaks again before a
  reply; at least one is present. Each side has `text`, `start_ms`, `end_ms` (offsets from call
  start, i.e. recording time zero) so the call detail page can sync transcript lines to the
  recording. `agent.text` is what was actually spoken (truncated at barge-in), plus `interrupted`.
  `timings` = `eot_ms, stt_final_ms, llm_ttft_ms, tts_ttfb_ms, v2v_ms` (null when a stage didn't
  happen; `v2v_ms` requires a user side).
- **Ordering.** `seq` is per call, from 0, assigned by the producer. The voice worker owns the
  in-call sequence; post-call producers start from the last persisted `seq` + 1 (they run after
  `call.ended` is stored). `UNIQUE (org_id, call_id, seq)` catches clashes.
- **Card numbers.** `build_event` redacts 13–19 digit, Luhn-valid runs (spaces/dashes allowed) from
  every free-text payload string; structural fields (phone numbers, ids, provider specs) are left
  alone. Spoken-out numbers in words are not caught; broader PII redaction is Phase 5.
- **Transport.** `EventEmitter.emit()` is synchronous and never awaits. A background task XADDs to
  the Redis Stream `vp:events`; while Redis is down, events wait in a bounded buffer (drop oldest,
  counted). At close, one time-limited flush.
- **Store.** `postcall.persist.EventPersister` (consumer group `persist`) validates, then inserts into
  `call_events` under `tenant_session(event.org_id)` with `ON CONFLICT (id) DO NOTHING`, updates
  `calls` on start/end, and acks after commit (at-least-once, idempotent). Permanent failures go to
  `vp:events:dead` with a reason; transient DB errors stay pending and `reclaim_stale()` retries
  them. The composite FK `(org_id, call_id) → calls` rejects events whose org doesn't own the call.
- **Tables.** `calls` (created by the API before the worker starts) and `call_events` (JSONB payload,
  event id PK), both standard tenant tables (0005). Partition `call_events` by month when volume
  requires it.

## Alternatives considered
- Separate `user_turn` / `agent_turn` events — latency between them would need joining; one exchange
  event carries it directly.
- Workers writing to Postgres directly — puts DB latency and outages in the audio path.
- Kafka/NATS — more infrastructure than needed; Redis is already required for queues.
- Unvalidated free-form events — the dashboard and webhooks would each guess the shape.

## Consequences
- Every producer and consumer shares one typed contract (Python + TS).
- Events are durable only after the consumer runs; a Redis outage longer than the buffer loses the
  oldest events of that call (logged with a count).
- Transcripts are stored raw (except card numbers) until Phase 5 redaction; tenant retention
  settings must cover `call_events`.
