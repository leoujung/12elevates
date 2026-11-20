# 12ELEVATE AI Network Building Intelligence
## Architecture Map v1.0 — Step 3 Deliverable (Pre-Implementation)

**Status:** DRAFT FOR REVIEW — no code, no migrations, no deployment yet.
**Governing documents:** Technical Architecture & Database Blueprint v1.0 + Product Experience & Member-Centric Development Principles v1.0.
**Decision basis:** Separate backend repo (approved). Existing `12elevates.com` stays untouched as marketing/inbound frontend.

---

## 1. EXISTING COMPONENTS TO REUSE

Verified in Phase 0 (not assumed):

| Component | Location | Reuse plan |
|---|---|---|
| Marketing/funnel website | `ingatsehat-network-funnel` repo, live at `12elevates.com` | Stays as-is. Becomes a **data source**, not a host, for the new backend. |
| Inbound capture points | `webhook-assessment.js`, `webhook-webinar.js` (Vercel functions) | These already receive lifestyle/business assessment + webinar signups. They become the **first two inbound integrations** into the new Prospect Intelligence API (Phase 1–2), replacing their current local-JSON/no-op behavior with a POST to the new backend. |
| Partner/member registry concept | `data/partner-registry.json`, `api/partner-resolver.js` | Conceptually this is a primitive, single-tenant version of `members` + `organizations`. It will be **migrated into PostgreSQL**, not kept as the system of record. The resolver's role (map a partner slug → WhatsApp/attribution) is preserved as a backend API, not a flat file. |
| Content guardrails | `ai-copilot.js` forbidden-claim patterns | Unrelated to prospect matching — this is a content-safety filter, not an AI engine per the blueprint. No action needed; stays in the website repo. |
| Opt-out handling | `opt-out.js` | Becomes the UI trigger for the new backend's `consent_records` / `suppression_list` tables (Section 5.1 E, M of blueprint) instead of its current standalone logic. |
| GA4 analytics | Already implemented and verified on the website (separate workstream) | Stays independent. Backend adds its own internal analytics (Section 11E) — the two are not merged. |

**Nothing from the existing stack is reused as infrastructure** (no existing DB, no existing auth, no existing backend framework) — because none exists yet. This is a greenfield backend build that integrates with a working frontend.

---

## 2. NEW COMPONENTS REQUIRED

### Backend (new repo)
- FastAPI application (Python) — modular monolith per blueprint Section 4.
- PostgreSQL database (Section 5).
- Redis (queue + cache) — introduced only when Phase 2 async jobs require it, not on day one.
- Alembic (or equivalent) for versioned, reversible migrations.
- Auth: JWT-based member authentication + RBAC (Section 6).
- Matching service module (deterministic scoring, Section 7).
- n8n workflows — reused from existing local n8n instance if feasible, or a dedicated instance for this project; decision deferred to Phase 2 (see Section 8 below).

### Frontend (new, separate from the marketing site)
- One **Member Intelligence Dashboard** web app (separate deployment from `12elevates.com`).
- 5 primary nav items only: Home, Prospects, AI Assistant, My Business, Academy (Product doc Section 4).
- Contextual drawers/modals/tabs instead of new pages for sub-workflows (Product doc Section 5).

### Integration layer
- A small, explicit set of webhook/API calls from the existing website into the new backend (detailed in Section 4 below). The website does not gain new business logic — it just forwards already-captured events.

---

## 3. PROPOSED REPOSITORY & PROJECT STRUCTURE

```
12elevate-ai-platform/              <- NEW repo, independent of ingatsehat-network-funnel
├── backend/
│   ├── app/
│   │   ├── api/v1/                  (routers: prospects, consent, matching, discovery, followups, analytics)
│   │   ├── core/                    (config, security, RBAC, tenancy middleware)
│   │   ├── models/                  (SQLAlchemy models matching blueprint Section 5)
│   │   ├── services/
│   │   │   ├── matching/            (customer_fit, business_builder_fit, leadership_fit)
│   │   │   ├── ingestion/           (inbound normalizer, dedup, consent check)
│   │   │   └── discovery/           (Phase 3 — Playwright workers, deferred)
│   │   └── main.py
│   ├── migrations/                  (Alembic, versioned + reversible)
│   ├── tests/                       (ownership, isolation, consent, dedup — Section 17 acceptance criteria)
│   └── requirements.txt
├── dashboard/                       (Member Intelligence Dashboard frontend — separate from marketing site)
│   └── src/ (5 nav sections, contextual modals/drawers)
├── docs/
│   └── ARCHITECTURE_MAP_v1.0.md     (this file)
└── infra/
    └── docker-compose.yml           (local Postgres + Redis for dev)
```

**Why a new repo and not a monorepo with the website:** the website is a live production asset with its own deploy cadence on Vercel. Keeping the backend separate means a backend bug or migration cannot accidentally break `12elevates.com`, and the two can be deployed, rolled back, and scaled independently — consistent with your Decision 1.

---

## 4. API INTEGRATION BETWEEN EXISTING WEBSITE AND NEW BACKEND

The website keeps capturing inbound events exactly as it does now. The only change (in a later phase, not now) is where that data goes.

```
12elevates.com (existing, unchanged)
   webhook-assessment.js  ───┐
   webhook-webinar.js     ───┤──►  POST https://api.12elevate-platform.<tld>/api/v1/prospects
   (future) referral form ───┘          (server-to-server, signed request, idempotency key)
```

- The website calls the new backend's public ingestion API. It does not get direct database access.
- Request signing (HMAC, similar to the existing `X-12ELEVATE-Signature` header already used in `webhook-assessment.js`) authenticates website → backend calls.
- The backend attributes the prospect to `source_type = inbound`, resolves `source_member_id` via the partner slug already captured by `partner-resolver.js`.
- **No change to the live website is made in this phase.** Wiring the actual POST call happens in Phase 1 (Foundation) at the earliest, and only after the backend's ingestion endpoint is built and tested — never against production without a rollback plan.

---

## 5. POSTGRESQL DATABASE & MEMBER-OWNED PROSPECT ARCHITECTURE

Directly from blueprint Section 5, phased:

**Phase 1 (Foundation) tables — built first, nothing else:**
`organizations`, `members`, `prospects`, `prospect_sources`, `consent_records`, `audit_logs`.

**Phase 2 (Intelligence) tables:**
`interactions`, `assessments`, `intent_signals`, `matching_results`, `assignments`, `campaigns`, `followup_tasks`.

**Phase 3+ tables (deferred until needed):**
`suppression_list`, `browser_discovery_jobs`, `browser_source_registry`, `import_jobs`, `deduplication_candidates`, `member_sharing_grants`, `regional_compliance_policies`, `data_subject_requests`, `model_versions`.

Ownership model: enforced at two layers, per blueprint Section 6 —
1. **API-level authorization** on every `/prospects/*` call (always required, built first).
2. **PostgreSQL Row-Level Security** as defense-in-depth (added once the core schema is stable — RLS policy bugs are easier to debug against a settled schema).

No table is created "because the blueprint lists it" — Section 5.2's explicit instruction ("document the reason for every additional table") is followed; unused modules stay out of Phase 1.

---

## 6. AUTHENTICATION, AUTHORIZATION, CONSENT, SECURITY

- **Auth:** JWT access/refresh tokens, password hashing via argon2 or bcrypt, member login scoped to `organization_id`.
- **Authorization:** RBAC per blueprint Section 6 role table (Member / Team Leader / Org Admin / Platform Admin / Compliance Admin). Enforced in FastAPI dependency layer before any DB query.
- **Consent:** `consent_records` is the single source of truth for lawful basis — no endpoint treats "the lead provider said they opted in" as verified consent (blueprint Section 5.1E explicit rule). Outbound-eligible status is computed, not assumed.
- **Security baseline for Phase 1:** TLS everywhere (inherited from hosting platform), encrypted-at-rest DB, secrets in environment/secret manager (never in code), rate limiting on auth and ingestion endpoints, structured audit log for ownership/consent/export actions (Section 14).
- **LLM data-handling rule carried over:** no prospect PII enters a third-party LLM prompt without an approved data-handling configuration (blueprint Section 14, last paragraph) — relevant once the AI Assistant / matching explanations (Phase 2+) start calling Gemini/Claude.

---

## 7. HOSTING, INFRASTRUCTURE, DEPLOYMENT & ESTIMATED DEPENDENCIES

Kept intentionally small for Phase 1 — no premature infrastructure (blueprint Section 4 explicitly forbids Kubernetes/microservices/Qdrant at this stage).

**DECISION (approved):** Self-host on the existing Hostinger VPS (ID 1964287 — Ubuntu 24.04, 8 GB RAM, 2 vCPU, 100 GB storage, Docker + Traefik already running the n8n instance at `n8n-n0ft.srv1964287.hstgr.cloud`). No new hosting account is opened; the new backend runs as additional Docker containers on infrastructure already paid for.

| Need | Proposed option | Why | Cost status |
|---|---|---|---|
| Backend hosting (FastAPI) | Docker container on the existing VPS, routed through the existing Traefik reverse proxy (new subdomain, e.g. `api.srv1964287.hstgr.cloud` or a custom domain pointed at the VPS) | Zero additional hosting cost; Traefik already handles TLS/routing for n8n, so the same pattern applies | **$0 incremental** — covered by the existing VPS subscription |
| PostgreSQL | Docker container on the same VPS (official `postgres` image, persistent volume) | 8 GB RAM / 2 vCPU is sufficient for n8n + FastAPI + Postgres at this project's expected Phase 1–2 scale; revisit sizing only if real usage shows contention | **$0 incremental** |
| Redis | Deferred to Phase 2 — add as another container on the same VPS when async job queues are actually needed | Avoids running unused infra | $0 until Phase 2, then $0 incremental (same VPS) |
| Dashboard frontend hosting | Vercel (new, separate project from the marketing site) — frontend static/SSR assets are lightweight and don't need the VPS | Consistent with your existing Vercel workflow/account; keeps the VPS dedicated to stateful services (DB, APIs, n8n) | Likely free tier sufficient initially |
| LLM provider | **Claude and ChatGPT (OpenAI)**, both via a configurable provider layer per blueprint Section 4 | Your decision — lets the matching/explanation service pick per use case (e.g. Claude for nuanced explanation text, ChatGPT for structured extraction) rather than being locked to one vendor | Usage-based (per API call); actual cost reported once Phase 2 matching/explanation volume is known — not estimated speculatively now |
| Monitoring | Sentry free/starter tier, or a lightweight self-hosted option (e.g. Uptime Kuma container on the same VPS) if you prefer to avoid even a free external account | Blueprint-specified (Section 4); self-hosted keeps everything on infrastructure you already control | $0–26/month depending on choice and volume |

**Operational trade-off, stated plainly (not glossed over):** self-hosting means *you* (not a managed provider) are responsible for Postgres backups, security patching, and making sure n8n and the new backend don't starve each other for CPU/RAM under load. At 8 GB RAM / 2 vCPU this is comfortable for Phase 1–2 (low-volume inbound + matching), but should be re-assessed before Phase 3 (Discovery + browser automation workers), which is more resource-hungry. A backup strategy for the new Postgres container (e.g. scheduled `pg_dump` to object storage) will be defined as a concrete task in Phase 1, not left implicit.

**n8n reuse (Decision 3, approved):** the existing n8n instance at `https://n8n-n0ft.srv1964287.hstgr.cloud` is reused for this project rather than standing up a separate instance. It already runs on the same VPS as the new backend, so workflow-to-API calls in Phase 3 (Section 12 events) stay on the local Docker network — no public internet round-trip needed between n8n and the backend API.

**No infrastructure will be provisioned or configured until you give the go-ahead to start Phase 1 build work.** This table reflects the approved plan, not infrastructure that has been touched yet.

---

## 8. FOUR-PHASE IMPLEMENTATION SEQUENCE

Mapped from blueprint Section 15 (6 phases) onto your requested 4-phase framing (Foundation, Intelligence, Automation, Global Scale):

### PHASE 1 — FOUNDATION
*(blueprint Phase 0 + Phase 1 combined)*
- New repo scaffolding, FastAPI skeleton, local Postgres (docker-compose) for dev.
- Core schema: `organizations`, `members`, `prospects`, `prospect_sources`, `consent_records`, `audit_logs`.
- Auth + RBAC + tenant isolation.
- Member Intelligence Dashboard shell: 5-nav skeleton, Home screen answering the 3 required questions (Product doc Section 4), no real data yet — placeholder states.
- **Acceptance gate:** blueprint Section 17 criteria #1–8 (ownership, isolation, consent recording) must pass before Phase 2 starts.

### PHASE 2 — INTELLIGENCE
*(blueprint Phase 2)*
- Wire the two existing webhook integrations (`webhook-assessment.js`, `webhook-webinar.js`) into the new ingestion API — **only after staging/testing, with explicit approval before touching the live site.**
- Build the three matching engines (Customer / Business Builder / Leadership) as deterministic, versioned scoring — Fit Score, Intent Confidence, Data Confidence kept separate (blueprint Section 7.4, non-negotiable).
- Dashboard: Prospects tab, AI Assistant recommendations, Follow-up Center — using contextual panels, not new pages.
- **Acceptance gate:** Section 17 criteria #10–13 (reproducible scoring, confidence separation, health-data isolation).

### PHASE 3 — AUTOMATION
*(blueprint Phase 3 + Phase 4)*
- Authorized External Discovery (only against sources with documented permission — Section 8 restrictions apply in full).
- n8n event-driven workflows (prospect.created → matching → notification → human-approved follow-up, Section 12).
- Follow-up task generation + member-approved outbound actions. No automatic messaging without explicit per-action member approval.
- **Acceptance gate:** Section 17 criteria #13–17 (quarantine, approved-source-only jobs, audit coverage).

### PHASE 4 — GLOBAL SCALE
*(blueprint Phase 5)*
- Localization (ID/EN first, schema already i18n-ready from Phase 1).
- Regional compliance policy tables, multi-currency/timezone.
- Matching model evaluation against real outcomes (the Section 7.2 weights are explicitly unvalidated hypotheses until this phase).
- Performance tuning, advanced analytics.
- **Acceptance gate:** Section 17 criteria #18–20 (backup/restore tested, full i18n, full test coverage).

Every phase ends with the Section 18 report format (Implemented / Tested / Pending / Blocked) before the next phase starts — no phase begins work ahead of the prior phase's acceptance gate.

---

## 9. PRODUCT PRINCIPLE COMPLIANCE CHECK

Quick trace from the 5 non-negotiable principles to this architecture, so nothing drifts later:

| Principle | How this architecture honors it |
|---|---|
| Simple to Use | Dashboard shell in Phase 1 is built around the 3-question Home screen and 60-second usability test — before any backend feature is "done," its dashboard surface must pass that test. |
| Know Who to Approach | Matching engines output reason codes + confidence, not a raw score — surfaced in the Prospects tab, not a separate analytics page. |
| Know What to Say | AI Assistant nav item (not a standalone chatbot page) houses conversation suggestions; member approval required before send, enforced at the API layer (no auto-send endpoint exists). |
| Know What to Do Next | Follow-up Center is a panel inside the dashboard, backed by `followup_tasks`, surfaced on Home as "Today's Priorities." |
| Easy to Replicate | Partner/member onboarding reuses the same schema regardless of tenure — no special-cased "leader" data model; Academy nav item is the single replication/training surface. |

---

## 10. DECISIONS CONFIRMED

1. **Repo:** `12elevate-ai-platform` — confirmed. Scaffold folder created at `C:\Users\ASUS\projects\12elevate-ai-platform\` (currently only `docs/` with this document; no code yet).
2. **Hosting:** Self-hosted on the existing Hostinger VPS (ID 1964287, Ubuntu 24.04, 8 GB RAM / 2 vCPU / 100 GB, Docker + Traefik) — see Section 7 for the full breakdown and the stated backup/maintenance trade-off.
3. **n8n:** Reusing the existing instance at `https://n8n-n0ft.srv1964287.hstgr.cloud` — same VPS as the new backend, so Phase 3 workflow calls stay on the local Docker network.
4. **LLM providers:** Claude and ChatGPT (OpenAI) both, via a configurable provider layer — no single-vendor lock-in.

**Remaining open item before Phase 1 build work starts:** none from this architecture map. Final go/no-go to begin Phase 1 scaffolding (repo init, FastAPI skeleton, local dev Postgres) is still required explicitly from you — this document being approved does not itself start implementation.

---

**END OF ARCHITECTURE MAP v1.0 — awaiting review and approval. No code, migrations, or deployment have been created.**
