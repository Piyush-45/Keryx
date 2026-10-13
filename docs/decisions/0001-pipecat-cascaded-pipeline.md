# 0001 — Pipecat with a cascaded STT → LLM → TTS pipeline

- **Date:** 2026-10-13
- **Status:** accepted

## Context
We need real-time phone agents that complete tasks, support Indian languages, and can be debugged
and evaluated per stage. Options were open-source frameworks (Pipecat, LiveKit Agents, TEN) and
speech-to-speech models vs cascaded pipelines.

## Decision
Use Pipecat as the orchestration framework with a cascaded pipeline (STT → LLM → TTS), with
providers swappable per tenant through our provider registry.

## Alternatives considered
- LiveKit Agents — strong at scale and native SIP; kept as the scale-up path if concurrency outgrows our setup.
- TEN Framework — lower-level, graph-based; more flexibility than we need now.
- Speech-to-speech models — lower latency and better prosody, but weaker task completion under
  noise/accents, no per-stage transcript, and vendor lock-in.

## Consequences
- Transcripts at every stage → evals, extraction, debugging are straightforward.
- Latency must be engineered (streaming, same-region hosting, turn detection) to stay under 1 s.
- Provider abstraction is required from day one so models can be swapped without pipeline changes.
