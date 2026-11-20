# Nyay Saathi: Android product upgrade and Supabase implementation handoff

Prepared for agy (Antigravity), 19 November 2026.

## 1. Outcome and fixed decisions

Build an Android legal-information and complaint-preparation assistant for India, retaining the current Nyay Saathi V2 React interface and upgrading its case, evidence, research and action workflows. The product should help a person explain a problem, understand supported options, prepare a complaint, take an authorized next step and continue the case later.

**This is the implementation brief.** The owner's original blueprint is preserved in [product-blueprint-reference.md](docs/plans/product-blueprint-reference.md). This handoff narrows release order, incorporates the actual implementation state and takes precedence over older infrastructure proposals. The original blueprint remains the broader product specification; it is not evidence that a feature has been implemented.

Fixed decisions:

1. **Protect the shared Vercel demo.** It has been sent to another person for review by the following weekend. Do not deploy to it, change its environment, migrate its database, replace its backend or push to its deployment branch. Do not infer an expiry date for this protection; only the owner can lift it.
2. Android is a **separate release**, using the current React UI bundled with Capacitor. Preserve the visual language, chat, drawers, language controls and existing useful interactions. Add screens and native behavior incrementally rather than redesigning the application.
3. **All application backend execution for Android belongs on Supabase.** The owner explicitly selected a backend rewrite over a separate Python host. Use TypeScript/Deno Edge Functions, PostgreSQL, Auth, and suitable Supabase job facilities. OpenAI and Google remain external provider APIs by design; a separate app server is not authorized.
4. Target project: `https://daojcrxjjkqoirqbvhjn.supabase.co`, organization **Nyay Sathi**, organization ID `eatddnxpdlcocibvfohd`. Current region is Tokyo, `ap-northeast-1`. Do not create/transfer projects, change regions or purchase upgrades without a concrete owner decision.
5. Do not touch the other Supabase project, `casmdqfgxoihjisrjsbk`, in **Riva**. It contains a separate health application.
6. Keep source work on `codex/android-supabase`, or an isolated branch/worktree derived from it. Browser development remains `VITE_BACKEND=legacy`; Android builds explicitly select `VITE_BACKEND=supabase`. Do not change Vercel's configuration to the Android values.
7. Preserve review, provenance, citation, dependency and case-write authorization protections during the rewrite. A smaller unreviewed chat-completion wrapper is not an equivalent migration.
8. No automatic external sending, filing, sharing, signing, payment or legal representation. Each supported external action must have the appropriate authorization and a truthful outcome record.

## 2. Actual starting point

| Area | Status as of this handoff |
|---|---|
| Existing V2 | Python/FastAPI primary reasoning agent, legacy selectable LangGraph, React UI, case memory, evidence extraction, drafts/exports, complaint journeys, research, review, voice and practice interfaces. Implemented paths are not blanket live-validation claims. |
| Android | Capacitor 8 source project generated in `frontend/android`; provisional app ID `in.nyaysaathi.app`; existing UI builds and assets sync. No APK/AAB compiled, signed or device-tested. |
| Frontend transport | Optional Supabase project URL/public key, lazy guest Auth session, bearer-authenticated API mapping and tests exist. Browser mode retains the existing API path. Native secure token persistence and account-linking are unfinished. |
| Hosted database | Seven foundation tables and an invoker RPC are applied to the Android project. RLS enabled on all seven; unauthenticated SELECT denied; client INSERT denied on trusted answer/memory/turn records. |
| Supabase API/AI runtime | **Not implemented or deployed.** There is no working `nyay-api` function yet. Hosted tables alone do not supply an operational backend. |
| Google integrations | Drive/Gmail product adapters, OAuth lifecycle and send approvals are not implemented. Connections in the development chat do not provide integrations to app users. |
| Knowledge | Existing corpus candidates, selected propositions, official law packs, recipient playbooks and research helpers. Broad Indian-law coverage and independent certification are not established. |
| Verification | Last recorded frontend/transport/embedded-Postgres run: 63 tests passed; React build and Capacitor sync passed. A targeted Python run had 50 passes and one date-dependent safety-contact failure. Re-run after changes; do not report these as new results. |

Read before modifying anything:

- [Current migration plan](docs/plans/android-supabase-migration.md)
- [Blueprint gap analysis](docs/plans/blueprint-gap-analysis-2026-11-19.md)
- [Hosted migration receipt](supabase/deployment-receipts/2026-11-19-foundation.md)
- [Foundation migration](supabase/migrations/20261119091306_android_backend_foundation.sql)
- [Hosted verification query](supabase/tests/foundation-verification.sql)

There are **uncommitted tracked edits and untracked files** from this work. Inventory and preserve them. Do not reset, clean, overwrite the working tree or assume only committed files matter.

The foundation was applied through the authenticated Supabase dashboard when the connector failed with `Unknown tool`. It may not appear in CLI migration history. Inspect the live schema and reconcile migration history before any push; blindly replaying CREATE TABLE statements will fail. Connector status is historical: recheck current access rather than requesting another connection automatically.

## 3. Product scope and release boundaries

The primary users are consumers and people facing payment/banking fraud or routine grievance problems. Secondary legal domains share the same architecture but need their own evidence and procedure coverage.

| Release | Required scope | Explicit boundary |
|---|---|---|
| **A — Internal Android parity** | Auth, private cases/chats, reviewed answers, citations, approved streaming, persisted retries, current supported evidence/draft/export/voice/practice contracts or an owner-approved capability matrix, installable test build. | Internal migration milestone. Not completion of the full product blueprint. |
| **B — Core consumer/fraud beta** | Reliable refund, defective-product, service complaint, active financial fraud and banking-payment workflows; maintained dossier; verified action cards; EN/HI/Hinglish; measured quality and latency. | Advertise only evaluated workflows and jurisdictions. General questions outside coverage can receive bounded help and uncertainty, not claims of comprehensive support. |
| **C — Complete P0 action workflow** | Optional user-owned Drive case folders, evidence manifests, Gmail evidence selection, reviewed/approved send, correspondence and confirmed outcome tracking, privacy/revocation controls. | Drive/Gmail were P0 in the owner's blueprint. Staging them later does not remove them from committed product scope. Do not call P0 complete before these work. |
| **D — P1 expansion** | Investment fraud, online abuse, travel, employment, tenancy/property, RTI/civic procedures, simple personal drafts; historical criminal-law references and relevant state coverage. | Each domain needs verified sources, procedures, test cases and an explicit coverage declaration. |
| **E — P2 research** | Judicial treatment, precedent analysis and complex disputes with professional-review pathways. | No autonomous adjudication, guaranteed remedies or advocate substitution. |

Across releases, users must be able to ask a general question without connecting Drive or Gmail. Do not require a full complaint intake when a question can be answered directly.

Desired product screens: three-action home (Know My Rights / Resolve a Complaint / Report Financial Fraud), existing conversational assistant, My Cases, case workspace, email review, verified contact cards, settings/privacy. The case workspace contains overview, evidence, legal basis, documents, communications, timeline and next actions, while retaining basic work inside chat.

## 4. Target architecture and invariants

```text
Android: existing React UI + Capacitor + native adapters
        |
        | HTTPS, Supabase Auth access token, stable request ID
        v
Supabase Edge API / bounded workers
        |-- authorization, tool policy, rate and spend limits
        |-- primary reasoning + selective research + claim review/repair
        |-- publication and persistent event replay
        |-- document and case services
        |-- Google OAuth / Drive / Gmail adapters
        |
        +-- PostgreSQL: private state, jobs, approvals, receipts, public legal metadata
        +-- public legal retrieval: full-text + evaluated vector retrieval/reranking
        +-- Storage: public legal snapshots; explicitly authorized temporary private artifacts
        +-- Cron/Queues: bounded refresh, ingestion, reconciliation and opted-in monitoring
```

Use logical services for triage, research, retrieval correction, applicability, planning, documents, Drive, Gmail, contacts and approvals. They do **not** each need a separate agent or LLM round trip. Retain a bounded primary session and use deterministic code for identities, exact citations, permissions, files, dates, hashes and action dispatch.

### Runtime feasibility is the first engineering gate

Edge Functions are a TypeScript-first Deno-compatible runtime. The existing Python graph, Tesseract, PDF libraries and local filesystem cannot simply be uploaded as-is. Check current [Edge Function limits](https://supabase.com/docs/guides/functions/limits) before choosing implementations. At this review, documented limits include 256 MB memory, 2 seconds CPU per request, and bounded worker lifetime. These are different from network/model wait time.

Prove the largest realistic PDF, image/OCR, source extraction, export and reviewed-answer workloads fit the selected runtime. A background callback, heartbeat or streamed HTTP connection does not remove a worker lifetime limit. Durable jobs must be composed of bounded checkpoints with leases, retry/recovery and cost controls. Do not split one indivisible CPU-heavy task into nominal queue messages and assume it now fits.

For difficult document work, evaluate Android-native extraction/OCR, bounded WASM or other compatible approaches with consent and integrity checks. Client-extracted text is untrusted and must retain the original hash and user correction history. Introducing a new external processing service requires a scoped owner decision and privacy disclosure; do not silently add a Python host.

[Supabase Compute](https://supabase.com/blog/supabase-compute-private-alpha) supports other runtimes but was private alpha, evaluation-only and region-limited at review time. It is not the production dependency for this Tokyo project. Reassess only if availability changes and the owner chooses it.

### Identity, persistence and jobs

- Supabase Auth identifies every user, including guest users. Add upgrade/link/recovery flows without moving another user's records. Use secure native storage for refresh credentials and other persistent secrets.
- Verify caller identity in every authenticated backend operation. Never authorize from editable user metadata. Use caller-scoped RLS for ordinary reads/writes; keep service-role credentials server-side and validate ownership before privileged operations.
- Cases are independent of conversations: one case can have several chats. Scope documents, jobs, drafts, events and approvals to user AND case; a case ID is not authorization.
- Preserve the existing distinction between public evidence, user allegations, document statements, approved output and authorized case patches. Answer approval must not independently authorize case-state writes.
- Use atomic RPCs/transactions for request admission, version checks, publication/commit and receipts. Existing client restrictions on trusted tables must remain intact.
- A retry with the same ID and same payload reuses execution; a changed payload conflicts. Stale workers must be fenced by a generation/lease token so that they cannot publish after recovery. Do not port local PID checks into the hosted runtime.
- Queue delivery and network retries can happen more than once. Promise observable idempotency through constraints and receipts, not exactly-once delivery from the transport.

Extend the foundation incrementally with documents/manifests, append-only case events, user actions, submission receipts, approvals/external actions, provider connections, contacts/procedures, legal documents/provisions/versions/relations, ingestion jobs, evaluation runs and operational counters. Store OAuth secrets separately from client-readable metadata. Public legal data and private case evidence must never share an unrestricted retrieval index.

### Streaming and response quality

Implement an event contract with execution/request ID, durable sequence number, event kind, block ID/revision, publication/check status and payload. Event kinds: `progress`, `safety`, `answer_block`, `result`, `error`; the exact wire schema must be versioned and tested.

The main pipeline is:

```text
Authenticate -> persist user turn -> immediate approved safety if eligible
-> retrieve context/evidence -> generate structured candidate
-> mechanical + dependency checks -> independent review when required
-> targeted repair/re-review -> compose/commit -> authoritative final result
```

Provider tokens and partial JSON are internal candidates, not publishable advice. Release approved templates and independently useful content only after all relevant gates, risk context and dependencies are established. Do not expose a legal recommendation whose qualifications depend on an unfinished later block or failed whole-answer coherence check. Batch review meaningful units; avoid an LLM call per sentence. More aggressive generation/review overlap requires evidence that it preserves the complete-answer checks.

Persist visible approved content before publishing its SSE event. On reconnect, resume after the last acknowledged sequence and deduplicate by execution/block revision. Never splice events from two executions. Cancellation, app backgrounding and a disconnected UI must not erase already delivered guidance or cause duplicate provider calls. Reconcile the live message with the final stored response and sources. Persisted content must be suitable for speech before TTS reads it.

For speed, improve context relevance, stable prompt prefixes, evidence reuse with freshness checks, concurrency of independent research, and concise machine-only output. Measure existing optimizations before duplicating them. Do not lower review quality or truncate output to meet an arbitrary latency target.

### Legal data and contact trust

Maintain official source snapshots, provision boundaries/hashes, jurisdiction, publication and effective intervals, repeal/supersession, amendment links, version relationships, known exceptions and review state. Unknown dates remain unknown. Mapping an old provision to a new one is not enough to decide applicability: evaluate incident date, procedural stage and verified transitional provisions.

Retrieve through exact section matching, keyword search, evaluated semantic retrieval, deduplication and reranking; expand surrounding definitions/exceptions where relevant. Record corrective findings for relevance, source authority, date, jurisdiction and completeness. A score or official hostname is not proof of legal applicability. Keep privacy-preserving, bounded live research for material gaps and current facts.

Schedule change detection, preserve previous versions, re-index affected provisions, review consequential changes and invalidate dependent caches. Do not label model agreement or a database flag “legal certification.” Source-origin checks, expert review, and applicability assessment are separate facts.

All phone, WhatsApp, email and portal destinations come from a normalized registry with official provenance, jurisdiction/category, verification timestamp, expiry and retired state. The model chooses a registry ID, not arbitrary contact text. Keep expiry suppression; refresh from sources rather than extending dates without checking them. Opening a dialer/portal/WhatsApp does not establish contact or filing.

### Drive, Gmail and user control

Drive connection is optional and incremental. Use the narrowest suitable scopes, initially evaluate `drive.file` and user-selected file access. OAuth scope and a folder are not substitutes for app-enforced owner/case boundaries. Preserve originals; create opaque case folders and a manifest with provider IDs, hashes, type, provenance and sync status. Handle moved, deleted, duplicate and revoked files.

Default private-original storage target is user-owned Drive. Supabase can hold necessary state/references and explicitly disclosed temporary extraction/artifacts with retention controls. If Drive is absent, general answers and text drafts still work; persistent server evidence storage requires an explicit disclosed product mode, not a silent fallback. Private extracted text remains private even when originals are user-owned.

Implement Gmail through an authenticated app backend adapter. Separate search/read, draft and send permissions, request them when needed, and plan Google's required verification. [Gmail scope rules](https://developers.google.com/workspace/gmail/api/auth/scopes) can affect public launch and server-side restricted-data handling; resolve them early, not after building the send UI.

Before send, show sender, To/Cc/Bcc, subject, full body and selected attachments. Bind approval to a versioned immutable payload hash, user, case, expiry and provider identity. Editing any material field invalidates approval. Never attach all evidence by default. Use a durable dispatch/outcome record; if Gmail may have accepted a message but the response was lost, reconcile before attempting another send. Do not claim that provider email send equals official grievance registration.

Optional reply monitoring is a separately consented feature. It can suggest a follow-up; it must not automatically send legal responses or escalate a case.

## 5. Ordered implementation work packages

Each package ends with runnable artifacts, evidence of its acceptance checks and an updated status document. Do not substitute a plan, mock response, configured environment variable or dashboard label for working behavior.

| ID | Work and deliverables | Completion gate |
|---|---|---|
| **0. Baseline and feasibility** | Inventory uncommitted changes, current UI/API contracts, deployed schema and migration history; record demo separation; reproduce tests; fix date-dependent safety fixtures with an injected clock; prove runtime feasibility for heavy document work and reviewed turns. Produce parity matrix, risk log and implementation estimates. | Existing demo remains unchanged. No blind schema replay. No unresolved claim that Python dependencies run in Edge Functions. Every current route is assigned an implementation/test or explicit owner-reviewed release deferral. |
| **1. Auth and durable cases** | Configure guest/account identity, secure Android session storage, account linking, case/chat APIs and transactional request lifecycle. Extend schema/RLS and protect editorial roles. | Two users cannot read or modify each other's records, link documents across owners, forge assistant/review/approval rows, or reuse a request ID with a different payload. New chat can reopen the same case. Worker restart/version conflict tests pass. |
| **2. Reviewed AI API and streaming** | Port structured schemas, provider continuation, research/safety tool policy, mechanical checks, semantic review, targeted repair, case patch authorization, composition/citations and accounting. Implement durable SSE/replay and live UI message rendering. | Real TypeScript implementation passes parity/failure fixtures; no unreviewed legal output; approved safety survives provider failure; final stored message matches display; reviewer failure preserves only eligible useful content. Live provider compatibility is separately verified within an owner-approved budget. |
| **3. Evidence, documents and Android parity** | Original/evidence metadata, runtime-compatible PDF/image extraction/OCR, correction/consent, drafts and native exports; port current voice and practice contracts or obtain explicit release deferral. Native back, keyboard, safe areas, external links and downloads/sharing. | A real test APK runs the intended Supabase backend. English/Hindi exports and extraction pass representative tests; originals/provenance preserved; deny-permission and interrupted-upload paths work. No feature silently disappears behind the unchanged UI. **Release A gate.** |
| **4. Core workflows and verified actions** | Complete consumer refund, defective goods, service complaint, active fraud and banking-payment journeys. Add the three entry points, My Cases, dossier/workspace and verified contact cards. Keep submissions, promises, processed refunds, remedy receipt and closure distinct. | Each advertised journey works from intake to a usable draft/next action and a later response update. Fraud bypasses routine merchant sequencing. Legal entitlement/eligibility depends on actual evidence. Contact cards use fresh registry records. **Release B gate.** |
| **5. Drive evidence management** | App-user OAuth, folder lifecycle, original upload/selection, case manifest, deduplication, reconciliation, open-folder UX, temporary-data cleanup and disconnect. Define handling of local V2 evidence; do not migrate it automatically. | Correct provider account/case every time; originals unchanged; missing/revoked access explained; duplicate retry safe; folder names minimize disclosure; no automatic sharing or permanent deletion. |
| **6. Gmail reviewed communications** | Scoped evidence search, selected correspondence import, editable review screen, payload-bound approvals, dispatch/reconciliation, thread IDs/replies, optional monitoring settings. | No send without current matching approval; recipient/body/attachment edits invalidate approval; ambiguous timeout cannot trigger blind resend; malicious email instructions cannot change recipients, tools or permissions. Provider/OAuth prerequisites are met. **Release C / full P0 gate.** |
| **7. Versioned legal knowledge and updates** | Strengthen central/state and historical-law records, exact mappings and temporal resolver, corrective retrieval, measurable semantic search/reranking, editorial provenance, source/contact refresh and cache invalidation. Required P0 evidence work begins during package 4; this is the systematic expansion. | Date/jurisdiction/exception conflicts produce supported answers or precise uncertainty. Removed/amended sources invalidate dependent output caches. No unsupported current-law or expert-certification label. Retrieval and legal scenario evaluation support the advertised coverage. |
| **8. P1/P2 and public rollout** | Add secondary domains one at a time, operational hardening, restore drills, privacy/security review, qualified legal review, accessibility, provider quotas, release signing and Play distribution. | Published coverage matches evaluations. Signed artifact and device tests pass. Deletion/revocation/retention/restore verified. Rollback does not overwrite the demo or erase evidence. Public release has an explicit owner go/no-go. |

Dependencies: 0 -> 1 -> 2 -> 3 -> Release A; 2 + 3 + core evidence -> 4 -> Release B; 1 + document foundation -> 5 -> 6 -> Release C. Legal-data/editorial foundations run alongside the core workflow work; they must not be deferred until after unsupported legal answers are advertised. Start Google verification preparation early while API migration proceeds.

## 6. Evaluation, performance and release evidence

Build a compact golden scenario set before optimizing models: refunds after return, defective products, exhausted support channels, failed payments, unauthorized debits, induced fraud payments, ongoing account compromise, changed facts, historical-law references, wrong state, unknown dates, source conflict, outside-coverage questions and mixed requests. Include English, Hindi and Hinglish. Add malicious PDF/email/web instructions, forged contacts/citations and cross-user object references.

Minimum test layers:

- Port the useful assertions from `backend/tests/test_primary_agent.py`, `test_primary_provider_transport.py`, `test_api_security.py`, `test_production_transformation.py`, `test_repair_and_drafts.py`, `test_documents_grounding.py`, `test_resolution.py` and related fixtures. Check behavior, not identical prose.
- Hosted RLS/auth tests in addition to the embedded tests in `frontend/src/supabase-rls.test.ts`. Test grants, policies, RPCs and the privileged API path; service-role testing alone does not establish RLS isolation.
- Mock-provider failure tests for refusal, truncated/invalid structured output, timeout, rejected citations, failed review/repair, queue redelivery, lease expiry and stale workers.
- Streaming tests for fragmented frames, duplicate/out-of-order delivery, disconnect at every stage, app background/resume, user retry and final reconciliation.
- Provider integration tests with test Google accounts and explicit recipients; do not send to real grievance officers as a test. Live LLM evaluations require explicit case/call/spend caps; prior session instructions prohibit unbudgeted paid evaluations.
- Device tests for microphone denial, file selection, keyboard, back navigation, Hindi fonts, OAuth return, app restart, network switching, native share/export and low-bandwidth behavior.

Measure time to first approved useful content, total response duration, p50/p95 per workflow, retrieval/review/repair timings, call counts, token/cache usage, cost/unknown usage, errors and duplication. Preserve quality scores for correctness, source support, applicability, completeness, usefulness and language quality. Compare the same scenarios before and after changes; offline fixture speed is not provider latency.

Carry the blueprint's aspirational targets forward for measurement: urgent approved fraud guidance under 3 seconds; common legal answer under 8 seconds p95; complex verified answer under 20 seconds p95 where achievable; initial draft under 30 seconds once facts are available; full preparation around 1–3 minutes excluding user interaction. These are targets, not promises or permission to skip checks. Rebaseline them after package 0 and account for the actual project region and device/network conditions.

No release is complete while critical ownership, approval, citation, urgent-safety, duplicate-action or evidence-loss failures remain. Automated passing tests do not replace appropriate legal review of consequential workflows.

## 7. Security, operations and truthful product behavior

Replace the bespoke encryption construction for the new backend with maintained authenticated-encryption/key-management components; preserve BYOK sealing behavior if BYOK remains the beta model. Review migrations and key rotation before transferring private records. Do not embed OpenAI keys, OAuth refresh tokens, service-role secrets or database credentials in the APK or `VITE_*` settings.

Use exact configured API origins; do not widen CORS to every preview domain. Treat files, fetched pages and emails as untrusted data. Enforce uploads and extraction resource limits, format validation, appropriate malware defenses and isolation. A regex flag is not a malware scanner or a prompt-injection authorization boundary.

Enforce project/user request and provider-spend budgets, not just in-process counters. Keep privacy-safe audit events and trace IDs without prompts, private files, raw email bodies, banking identifiers or credentials in operational logs. Check actual behavior before asserting that data is encrypted, physically purged, retained for a fixed period, professionally reviewed or compliant with a regulation.

For each deployed component, distinguish configured, connected, healthy and tested. Add metrics/alerts and a tested restore procedure. Keep reversible schema changes and backup/rollback evidence. Define cleanup for temporary artifacts and revoked provider connections. User-reported contact, sent email, captured receipt and official filing confirmation are different event types.

## 8. Owner inputs and genuine external dependencies

Proceed with independent implementation without repeatedly asking for routine choices. Record open decisions with defaults and the phase they block:

| Input | Proposed treatment | Needed before |
|---|---|---|
| Runtime/document feasibility | Prove a Supabase-only implementation; if an essential operation cannot fit, present a measured limitation and bounded alternatives. Do not silently add another host. | Final package 0 architecture |
| Region/data handling | Preserve the existing Tokyo project. Explain measured latency/data-location implications; move only on explicit instruction. | Public launch or any proposed region change |
| App identity | `in.nyaysaathi.app` is provisional; confirm final package ID, developer identity, signing custody and Play account. | First signed release |
| Model funding | Preserve existing BYOK as the continuity default unless the owner chooses managed usage and a budget. Costed model changes require evaluation. | Public beta and paid live tests |
| Google setup | Owner-controlled Cloud project, OAuth consent/redirect configuration, test users, scope verification and any applicable review. | Releases involving Drive/Gmail |
| Evidence/privacy policy | Drive-owned originals; disclose temporary processing and metadata. Any alternate permanent storage model needs an explicit decision. | Persistent evidence release |
| Legal review/coverage | Qualified review and explicit domains/states supported. | Advertising evaluated legal workflows |
| Publishing | Internal builds are not public store approval. Prepare artifacts and a concrete release report before requesting public publication. | Public release |

Do not promise delivery dates before the runtime proof and route inventory. At the end of package 0, give engineering estimates by package and separately list Google verification, legal review, account access and store-review lead times.

## 9. Required handoff and execution discipline

For each package, deliver source/migrations, API/schema changes, tests and exact results, a brief demonstration, remaining limitations and a rollback/recovery note. Update a feature-parity matrix with statuses: not started / implemented locally / tested locally / deployed / verified hosted / release-ready. Do not collapse these into “done.”

Keep a ledger in `docs/plans/agy-upgrade-status.md` with the active package, files changed, deployed project/function versions, migration receipts, exact commands/results and next unresolved dependency. Never include secrets in that ledger. This enables another developer to resume without reconstructing chat history.

First concrete deliverables from agy:

1. Confirm the Vercel protection and inventory the current working tree.
2. Inspect the intended Supabase project, reconcile the applied foundation and report advisor findings without modifying unrelated projects.
3. Produce the route/capability parity matrix and runtime feasibility results.
4. Implement the first vertical slice: Android Auth -> private case/chat -> durable reviewed turn -> approved stream -> persisted/replayed result.
5. Demonstrate two-user isolation and disconnect/retry behavior, then extend that working slice through evidence, drafts, workflows and Google actions in the package order above.

Do not declare the product finished because a container opens the current UI, an LLM responds, seven tables exist or an APK installs. The completion criterion is the tested user journey and its stated release scope.
