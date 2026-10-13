# Roadmap

Sellable (paid, managed pilots) at **week 14**. Self-serve launch ~week 20.
Assumes one full-time builder with AI-assisted coding. Tick boxes as work lands.

## Phase 0 — System design (weeks 1–2)
- [ ] Pick 1–2 launch industries; list 15–20 target businesses
- [ ] Architecture written (docs/architecture.md) and reviewed
- [ ] Tenant model + Postgres RLS design
- [x] Agent config JSON Schema (versioned)
- [ ] Provider registry interface + fallback order
- [ ] Call event model
- [ ] Latency budget per stage; region choice
- [ ] Recording/transcript storage + retention plan
- [x] Repo scaffold: api/, workers/, dashboard/, packages/shared/, CI with lint + tests

## Phase 1 — Core voice engine (weeks 2–5)
- [ ] Pipeline factory: config JSON → running Pipecat pipeline
- [ ] Telephony: Plivo + Twilio, inbound + outbound
- [ ] Adapters: Deepgram, Sarvam (STT); OpenAI, Gemini, Claude (LLM); Cartesia, ElevenLabs, Sarvam (TTS)
- [ ] Turn detection + barge-in tuned on Hindi, English, Hinglish
- [ ] Tool calling over HTTP + Pipecat Flows states
- [ ] Filler lines for slow tools
- [ ] Warm transfer to human
- [ ] Recording, transcript, per-turn latency logging
- [ ] Load test: 20 concurrent calls on one machine
- **Gate — Demo-ready:** agent books a Google Calendar appointment by phone, Hindi + English, median < 1s

## Phase 2 — UX/UI design (weeks 3–5, parallel)
- [ ] Personas: ops manager, business owner, builder/agency, call reviewer
- [ ] Prototype flows: template → first agent; CSV → campaign; call review; enriched export
- [ ] Design tokens + components (shadcn/ui), empty/loading/error states
- [ ] Prototype tested with 3 prospects

## Phase 3 — Platform MVP (weeks 6–10)
- [ ] Auth, orgs, roles
- [ ] Agent builder + versioning + templates + playground (browser + "call my phone")
- [ ] Voice presets with latency/cost badges; BYOK
- [ ] Phone numbers attach/buy → agent
- [ ] Calls list + call detail (synced audio/transcript, tool timeline, latency, cost)
- [ ] Post-call worker: summary, typed extractions, dispositions + confidence
- [ ] Review queue
- [ ] Signed outbound webhooks with retries
- [ ] Usage metering per tenant
- **Done when:** new company onboarded in < 30 min, no code changes

## Phase 4 — Campaigns + integrations (weeks 11–14) → SELLABLE
- [ ] CSV/Excel upload, column mapping, E.164 validation, dedupe
- [ ] Columns as {variables} in prompt/greeting
- [ ] Scheduler: windows, concurrency cap, pause/resume
- [ ] Auto-retry (no-answer/busy/failed, 30+ min gaps), voicemail detection
- [ ] Callback matching to campaign row
- [ ] Live campaign board + enriched export
- [ ] India compliance: DND scrub, 140/160 numbers, consent field
- [ ] Google Calendar + Cal.com
- [ ] One CRM deep (Zoho or HubSpot): import, write-back, call log
- [ ] n8n + Make connectors
- [ ] Funnel analytics + cost per outcome
- **Gate — Sellable:** 2–3 design partners on paid, managed pilots

## Phase 5 — Production hardening (weeks 15–20)
- [ ] Eval suite per agent; regression on every prompt/model change
- [ ] Per-call traces + alerts (P95 latency, error spikes)
- [ ] Live provider fallback mid-call
- [ ] Secrets vault, PII redaction, retention settings, audit log
- [ ] Billing: Razorpay + Stripe, prepaid credits + usage
- [ ] Self-serve onboarding, docs, API keys
- [ ] Autoscaling to 100+ concurrent calls
- **Gate — Self-serve launch**

## Phase 6 — Scale and expand (week 20+)
- [ ] Salesforce, GoHighLevel, LeadSquared, Zendesk, Freshdesk, Drive/Notion KB
- [ ] WhatsApp follow-ups via tenant's own BSP
- [ ] Second industry templates
- [ ] Objection mining, script A/B tests, best-time-to-call
- [ ] Agency mode (sub-accounts, white-label)
- [ ] Public API + SDK
- [ ] Payment-link tool (only if collections is a target industry)
