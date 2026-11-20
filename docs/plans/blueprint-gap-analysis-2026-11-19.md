# Nyay Saathi V2: blueprint gap analysis

Assessment date: 19 November 2026.

Compared the supplied “Complete Product Design & Technical Blueprint” with the current repository. This is a source-code assessment plus targeted offline tests, not a production, legal-correctness, accessibility, or live-provider certification. No paid model calls or external account actions were performed. Application code was not changed.

## Overall assessment

Retain V2's React/FastAPI interface, primary reasoning runner, evidence registry, response review, complaint journey, document preparation, and durable turn protocol. Upgrade these incrementally.

The principal gaps are user identity and independent case IDs, user-owned Drive storage, approved Gmail actions, structured contact actions, legal version resolution, production persistence, and verified incremental answer delivery. These require backend contracts and data migrations as well as interface work.

Status terms: **Implemented** means a concrete code path exists; **Partial** means the blueprint requires more than that path supplies; **Missing** means no implementation was located in the inspected application. Implemented does not mean live-validated or production-ready.

## Feature comparison

| Blueprint area | Current implementation | Upgrade required |
|---|---|---|
| Conversation and languages | Implemented: React chat, English/Hindi/Hinglish, history, attachments, source drawer, voice interfaces and practice mode. | Validate live voice/OCR and accessibility; add the three intent-based entry points without making account connection mandatory for questions. |
| Main response streaming | Partial: progress and persisted approved safety SSE; roleplay has text deltas. Main provider collects a complete structured answer and UI reloads after completion. | Add provider streaming, explicit approved answer-block events, live assistant rendering, durable replay and final reconciliation. Preserve legal review. |
| Intake and case memory | Implemented: task interpretation, source-attributed facts, contradictions, staged updates, version checks, continuity and request coverage. | Distinguish an independently maintained case from a chat; minimize questions to the facts needed for the next decision. |
| Consumer complaints | Substantial foundation: consumer corpus, platform playbooks, conditional routes, complaint events, draft preparation and outcome distinctions. | Validate complete refund/defective-product journeys and current recipient/eligibility data. Preserve uncertainty where procedural eligibility is unresolved. |
| Financial fraud | Partial: mechanism-specific urgent detection, protective templates, early safety delivery, fraud-related propositions. | Complete transaction-type distinctions, current regulatory evidence, bank-specific verified contacts and complaint workflows. Do not infer reimbursement entitlement from a fraud label. |
| Banking/payments | Partial: some routing, evidence and regulator preparation. | Build a complete versioned banking procedure pack, prior-complaint prerequisites and scenario tests for failed, unauthorized and induced payments. |
| Other legal domains | Partial: selected criminal, employment, legal-aid and Bihar materials plus dynamic research. | Treat each domain/state as an explicit coverage expansion with representative tests. Full tenancy, RTI, investment, cyber-abuse and historical-law coverage is not established. |
| Case workspace/dossier | Implemented foundation: facts, timeline, evidence preview/correction, journey, drafts, actions, submission steps, escalation bundles and exports. | Expand into My Cases and a workspace with communications, legal basis and Drive files. Add independent case IDs, multiple chats per case, and a confirmed lifecycle projection. |
| Drive | Missing: no Google OAuth/Drive application adapter or case-folder lifecycle found. Uploads currently persist to the backend filesystem. | Optional Google connection; app/case-scoped folder/file mapping, original preservation, hashes, manifests, reconciliation, revocation and explicit storage policy. |
| Gmail | Missing: no application Gmail OAuth, search/send adapter, approval records or thread integration found. | Scoped search, evidence selection, editable email preview, approval bound to the exact payload, idempotent dispatch and confirmed Gmail IDs. Changed recipients/body/attachments invalidate approval. |
| Contact/action cards | Partial: recipient playbooks and dated safety-contact constants. No general normalized verified-contact service or call/WhatsApp cards located. | Registry with official provenance, jurisdiction, eligibility, verification expiry, retired status and refresh jobs; render destinations from registry records. Opening an external app is not proof of contact/submission. |
| Legal retrieval | Implemented foundation: BM25; optional Chroma embeddings/RRF; authority-aware local search; remote OpenSearch text-search path; exact source/locator metadata and source packs. | Benchmark semantic retrieval and reranking, exact provision matching, exception/definition expansion, and applicability filtering. Local trigram matching is not learned semantic retrieval; a remote text query alone is not remote vector search. |
| Corrective retrieval | Partial: primary agent can request research, evaluate supplied material, repair and qualify missing support. | Introduce explicit relevance/authority/version/jurisdiction/exception findings and a bounded corrective loop. Prefer deterministic checks where possible; avoid adding a separate LLM call for every logical role. |
| Historical laws/versions | Partial: effective dates, amendment notes, treatment labels and an optional as-of retrieval filter. | Versioned provision records, repeal/supersession intervals, amendment and predecessor/successor relationships, incident-date routing and verified transitional rules. Current date filtering is not a complete historical resolver. |
| Continuous updates | Partial: acquisition/build scripts and expiring public evidence cache. | Scheduled source checks, change detection, preserved snapshots, affected-section indexing, review queue and dependent-cache invalidation. |
| Identity and permissions | Partial: guest ownership, signed device tokens, CSRF and per-conversation checks. | Persistent application users, guest-to-account migration, Google-connection ownership, role-based editorial access, and per-case permissions independent of browser cookies. |
| Privacy and file security | Partial: per-case encryption code, attachment consent, encrypted transfer, deletion/key-destruction paths, byte-pattern upload checks and untrusted-text flags. | Replace the bespoke SHAKE/HMAC encryption construction with a maintained authenticated-encryption implementation and migration plan; managed keys/secrets; sandboxed extraction and real scanning; verify retention/purge behavior and metadata minimization. Pattern detection alone does not establish isolated malware scanning. |
| Production infrastructure | Partial: SQLite persistence, local locks/rate limits, configuration fields and readiness output. Actual remote OpenSearch request code exists. | Implement and exercise PostgreSQL repositories/migrations, distributed coordination, background workers, appropriate object storage and telemetry exporters. DSN/URL flags and queue descriptions do not implement adapters. |
| Evaluation and operations | Implemented offline tests, fixtures, budgets, call telemetry and evaluation entry points. | Paired latency/quality benchmarks, expert review, connector sandbox tests, multi-instance and disaster-recovery tests, real accessibility/OCR/voice checks and monitored release gates. |

## Evidence and important qualifications

- `backend/app/runtime.py` selects `PrimaryAgent` by default. LangGraph is retained as the legacy engine. The primary runner uses its own bounded reasoning/research loop and durable turn persistence; it does not create a LangGraph checkpoint. Do not rebuild the system as ten serial agents merely to match the blueprint's role names.
- `backend/app/db.py` uses SQLite directly. Its case memory and attachment ownership are keyed by `conversation_id`; there is no independent maintained-case model yet.
- `backend/app/platform/adapters.py` mostly describes intended infrastructure and reports mode from configuration presence. PostgreSQL, Redis, object storage and Temporal settings are not proof of remote execution. The active local database and in-process abuse controller remain explicit code paths.
- `backend/app/services/documents.py` writes attachment bytes to the backend filesystem, optionally encrypted. This differs materially from the blueprint's user-owned Drive originals and limited-retention processing promise. Offer an explicitly disclosed local mode during migration; do not claim that the current storage model is Drive-based.
- Corpus files currently contain 14 curated consumer passages, 607 ingested passages, 15 proposition records and 43 official-pack passages. Proposition certification labels are metadata, not independent evidence of qualified review. These counts do not establish broad Indian-law coverage.
- `backend/app/knowledge/search_index.py` checks commencement against an optional date but is not a full repeal/version/transitional-rule resolver. Missing effective dates can currently remain eligible for retrieval; generation must not interpret that as proof of applicability.
- Editorial decision endpoints in `backend/app/main.py` have CSRF checks but no reviewer-role authorization in those endpoint definitions. Reviewer name/enrollment strings and stored approval labels do not establish reviewer identity. Protect these before treating editorial decisions as trusted public knowledge.
- Some language/readiness metadata asserts auditing or operational capabilities. Require the corresponding test/review evidence before presenting those labels as achieved guarantees.

## Recommended implementation order

### 1. Establish an honest, reproducible baseline

Resolve time-dependent safety tests with an injected/fixed clock, preserve stale-contact suppression, and add a verified contact-refresh process. Make readiness distinguish configured, connected, healthy and exercised. Protect editorial operations; plan encryption/key migration before onboarding real sensitive accounts. Record current latency and quality on representative consumer and fraud cases.

Acceptance: deterministic offline tests; expired contacts cannot silently appear as current; editorial writes require authorized roles; reported readiness matches actual adapters. Live evaluation is a separately budgeted activity.

### 2. Deliver response speed improvements

Wire structured provider streaming to internal candidate accumulation. Publish approved, independently useful blocks with stable IDs; retain full review/coherence gates for consequential legal advice. Persist visible blocks before delivery; support interrupted streams, retries and final-message reconciliation. Measure cache effectiveness and remove duplicated context. Investigate overlap of fetching with completed searches while preserving source ranking and budgets.

Acceptance: first approved content arrives before turn completion when eligible; no unreviewed legal conclusion leaks; reconnects do not duplicate content; final saved text and citations match displayed content. Measure first approved content and total response separately.

### 3. Build the production identity and case foundation

Introduce users and independent cases, migrate existing conversation-linked records, and allow more than one chat per case. Add PostgreSQL-backed repositories with explicit schema migrations and durable pending operations. Preserve existing ownership, version, replay and receipt semantics. Add optional OAuth connection ownership and token lifecycle.

Acceptance: existing cases survive migration, cross-user/cross-case access fails, a case reopens from a new chat, and retry/worker restart cannot duplicate durable effects.

### 4. Add the action layer

Build Drive case-folder/file management, evidence manifest and missing-file reconciliation. Define how local stored evidence migrates and when temporary copies/extracted text expire. Add the normalized contact registry and action cards. Then build Gmail search, draft review and approved send with exact payload hashes, selected attachments and durable action receipts. Keep sent email, user-reported portal filing and confirmed official submission separate.

Acceptance: correct user/case folder only, no duplicate uploads, originals unchanged, no send without matching approval, no attachment disclosed merely because it exists, and ambiguous send outcomes require reconciliation before retry.

### 5. Deepen the legal-data system and release workflow by workflow

Prioritize consumer refund, defective goods, financial fraud and banking complaints. Add incident-date/version resolution, verified procedures and contacts, source update workers and explicit corrective retrieval diagnostics. Expand domain/state coverage only when evaluation supports it. Introduce a new vector store or reranker only after retrieval measurements identify a concrete gain; avoid operating multiple search systems without a demonstrated need.

Acceptance: jurisdiction/date/exception test suites, reviewed source coverage for each advertised workflow, current contacts, traceable evidence, and before/after quality and latency reports. The blueprint's under-8-second common-answer p95 is a target requiring measurement, not an achieved result.

## Verification performed for this assessment

Executed:

```sh
cd backend
uv run pytest -q tests/test_primary_agent.py tests/test_production_transformation.py tests/test_api_security.py
```

Result: **50 passed, 1 failed**. The failing test is `test_safety_is_durable_before_provider_failure_and_deduplicated`: it expects a contact number, while the runtime suppresses the contact after the record's `revalidate_after` date of 14 November 2026. Safety text still persists and streams. The correct remediation is verified refresh plus deterministic expiry tests, not extending verification dates without checking sources.

No full suite, live provider benchmark, Google integration, public-source revalidation or deployment was performed in this assessment.
