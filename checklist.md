# Nyay Saathi MVP checklist

Updated 20 November 2026. Shared tracker for work undertaken through Codex and Antigravity. This records scope, existing evidence, remaining work and integration gates; it does not dispatch work to either tool.

## A. Product decisions

- [x] Keep the shared Vercel demo protected and develop Android separately.
- [x] Retain the current React UI in the Capacitor Android app; use Supabase for application backend execution.
- [x] Plan for the confirmed Free-plan runtime: persisted, resumable agent steps instead of one long request.
- [x] Include Google-only sign-in in Android, with profile confirmation and optional Google service connections during onboarding.
- [x] Include Drive, Gmail, Calendar, and optional location/nearby-place features in the product scope.
- [x] Support ordinary assistance without requiring Gmail, Drive, Calendar or location permission. Android sign-in itself uses Google.
- [x] Keep exact email/calendar action approval separate from permission to connect a service.

Checked items in this section are accepted decisions, not claims that the corresponding features are implemented.

## B. Workstreams and status

Use these statuses: **planned → in progress → implemented locally → tested locally → verified hosted/device → accepted for demo**. Add **blocked** with the specific missing dependency where necessary. Code built with mocks is not verified provider functionality.

| Workstream | Owner | Status for new acceptance gate | Current evidence | Remaining acceptance gate |
|---|---|---|---|---|
| Legal database and retrieval | Antigravity | Planned; assigned, not dispatched from this chat | Selected legal packs and retrieval code exist; full hosted vector/corpus coverage is not established | Reviewed initial corpus, version/region filters and representative retrieval tests |
| Google services | Unassigned | Blocked: Cloud setup and adapter corrections | Local Drive/Gmail scaffolding; critical false-success paths identified; Cloud project not yet created; Calendar is newly added scope | Actual authorized provider operations, receipts, revocation and error handling |
| Agent reasoning and verification | Backend & Agent Integration — Codex chat | Tested locally with raw HTTP and delayed provider fixtures | Strict primary/review/repair validation, bounded tool continuation, evidence gates, targeted repair and atomic approval | Antigravity retrieval integration, quality evaluation and authorized provider smoke test |
| Supabase execution and identity | Backend & Agent Integration — Codex chat | Tested locally with PGlite | Transactional outbox, fenced leases, recovery, cancellation, owner-scoped replay and over-200-second simulated run | Hosted migration, runtime measurement and Android device replay |
| Cases, documents and actions | Unassigned | Implemented locally; correction required | Existing case/draft workflows plus newer local screens; document defects identified | Complete evidence-to-approved-action workflow with truthful outcomes |
| Google-only onboarding and Android UI | Unassigned | Planned | Current React UI and Android shell; reviewed code still uses guest/account-linking behavior | New login/onboarding flow, real OAuth return, session restore and device checks |
| Quality, security and accessibility | Unassigned | Tested locally; wider gates open | Last independent selection: 98 frontend tests, 51 Python tests and frontend build passed | Boundary regressions, legal quality checks, Hindi exports and end-to-end/device tests |
| Deployment and operations | Unassigned | Planned | Initial Supabase foundation verified previously; no full Android backend acceptance | Hosted receipts, installed APK, budgets, monitoring and rollback |

The owner assigned Antigravity to legal knowledge/retrieval and the dedicated **Backend & Agent Integration** Codex chat to resumable backend/agent work on 20 November 2026. This labels the intended executor; it does not claim that a chat has been created, renamed in the app, dispatched or started. Other workstreams remain unassigned.

### 1. Legal database and retrieval

- [ ] Define a bounded consumer/fraud/banking corpus for the prototype.
- [ ] Store official source, provision locator, region, effective dates, amendment links and review state.
- [ ] Import/index the real corpus and implement the chosen lexical/vector retrieval contract.
- [ ] Test national + state applicability, unknown dates/regions, exceptions and missing evidence.
- [ ] Define source-refresh and editorial-review responsibilities.

### 2. Google services

- [ ] Owner creates the Google Cloud project and records its project ID.
- [ ] Configure OAuth clients, real signing fingerprints, callbacks, test users and selected scopes.
- [ ] Enable Gmail, Drive, Calendar and the selected Maps services; configure billing/quotas as applicable.
- [ ] Replace false-success Drive/Gmail paths with actual provider adapters.
- [ ] Implement optional Calendar reminders, initially evaluating an app-created calendar with narrow access.
- [ ] Implement region suggestion and nearby-place discovery with manual override and authoritative contact verification.
- [ ] Verify real upload/send/event receipts, token refresh/revocation, missing scopes and ambiguous outcomes.

### 3. Agent

**Hosted semantic qualification, 20 November 2026.** Backend owner. See [the benchmark report](docs/plans/hosted-e5-qualification-2026-11-20.md) for probe receipts, exact artifact digests, reproduction and rollout prerequisites.

| Finding | Evidence and implication | Severity and next action |
|---|---|---|
| Dedicated Supabase E5 failed both attempts | Tokyo cold requests took 17.56 s and 17.92 s. Exact model download and SHA-256 verification took about 12.1 s each. The first WASM loader rejected its HTTPS module, and the package-local loader rejected shared memory. Neither returned embeddings. Supabase exposed heap and external allocation only, so hosted peak and warm inference timing remain unmeasured. | **8/10**, blocks semantic release. Stop this approach. Accept no lexical-only fallback and leave admission unavailable. |
| Local artifact and multilingual ranking | Native ONNX and local WASM produced 384 values from the original tokenizer. Cosine agreement was 0.99738–0.99811. The expected English, Hindi and Hinglish passages kept hybrid ranks 2, 1 and 4 in local SQL. Native peak process RSS was 653 MB and the WASM run peaked at 722 MB. | **0/10 for this local parity slice**. Repeat against the approved managed candidate with cold, warm and privacy checks. |
| Managed inference option | A protected Hugging Face CPU container can use the same pinned ONNX artifact and tokenizer. Propose one replica, at most 24 billable hours and a verified US$2 incremental spend cap. Query text would be processed by an additional provider. | **8/10 until qualified**. Verify the cap, terms, region, request logging and exact model parity before provisioning or sending any case data. |
| Hosted state and cleanup | Qualifier version 3 returns HTTP 410. The target had the foundation table, an empty migration ledger and no application function. The resumable migrations, corpus seed and Sol evaluation were gated and were not run. Sol Medium, budget reconciliation, observability and the Vercel demo were unchanged. | **8/10 for release verification**. Qualify inference, then reconcile the migration ledger and run restricted budget-capped verification. **1/10** inert route remains registered. Remove it later with project CLI credentials. |


**Legal retrieval integration, 20 November 2026.** Backend owner. Antigravity’s legal worktree remains the source for corpus, evaluation and editorial refresh. The backend worktree now runs the real SQL hybrid retriever. The [rollout](docs/plans/legal-retrieval-integration-rollout.md) lists changed surfaces, exact project commands, dependencies and rollback.

| Change or remaining issue | Implication and local evidence | Severity and next action |
|---|---|---|
| Real corpus and hybrid retrieval | Owner approved `text-embedding-3-small` at 384 dimensions after hosted E5 failed. All 50 passages, the guarded seed, Edge bundle, migration predicate and query fixtures now use version `openai:text-embedding-3-small:dimensions=384:v1`. The full SQL hybrid gate passed 15 inherited cases covering English, Hindi, Hinglish, temporal and unsupported queries; a separate null-incident current-law case passed. The reviewed journey still completes with citations and reconnect replay. | **0/10** for the exercised local hybrid flow. Run corpus and ACL verification on the intended project before enabling admission. |
| Missing incident date | Clearly general questions use the as-of date while the incident date stays null. An undated incident supplies no time-bound evidence. A confirmed historical date selects the historic regime, and companion passages remain together even in research continuations. | **4/10** residual classification risk. Conservative language cues can withhold support from ambiguously worded general questions. Extend evaluation with real anonymized phrasing before broad rollout. |
| Hosted semantic execution | The Edge worker now calls OpenAI directly with model, 384 dimensions, bounded body, three-second timeout, redirects disabled and strict response validation. Each request includes a recorded canary; cosine below 0.99999 fails closed. Corpus rebuilding checkpoints by content hash and replayed with zero duplicate provider requests. | **5/10** alias-drift availability risk. Canary prevents silent mixing but a provider change requires full re-embedding and requalification. Admission stays paused pending hosted checks and spend control. |
| Embedding budget and observability | Corpus rebuild used 22,369 input tokens over four successful requests. A Python 3.9 writer failure caused one deliberate four-request repeat before checkpoints existed. Two small query qualification calls were made. Sol Medium defaults and its SQL reconciliation were unchanged, but embedding calls are not charged to that ledger. | **8/10** release blocker. Verify an OpenAI project hard cap or extend durable SQL accounting before enabling admission; record embedding request/token metrics in hosted observability. |
| Hosted and legal release evidence | Migration, guarded seed and verification SQL are prepared. No hosted migration, deployment, secret update, Sol live evaluation, legal quality review or Android device check was performed in this slice. OpenAI query data may have default abuse-monitoring retention up to 30 days unless ZDR is approved/configured. | **8/10** release blocker. Confirm cap and retention decision, then execute the hosted checklist on `daojcrxjjkqoirqbvhjn` with admission paused. |
| Existing frontend bundle warning | Build completes. Vite reports an existing chunk over 500 KB. | **2/10**. Defer unless device measurements show an issue. |

Local checks after the OpenAI switch: `npm test -- --maxWorkers=1` passed **157 tests across 20 files**. This includes all 15 inherited retrieval cases, a null-incident general-current citation case, canary drift rejection, the reviewed reconnect journey, service-only RPC access and guarded bootstrap. `npm run build` passed with the existing chunk warning. `npx --yes deno check --sloppy-imports supabase/functions/nyay-api/index.ts` passed on Deno 2.9.6. Generation and review remain separate provider fixtures; no live Sol quality claim is made. The protected Vercel demo was left intact. Detailed evidence is in [the OpenAI embedding qualification](docs/plans/openai-embedding-qualification-2026-11-20.md).

Backend worktree on 20 November 2026: `/Users/ashutoshanand/Downloads/Nyay-Saathi-backend-resumable`, branch `codex/resumable-backend`. Backend owns `supabase/functions/nyay-api/` provider and turn execution files, the resumable SQL and operations script, the retrieval interface and test fixtures, and the minimal frontend API and chat transport. Antigravity owns the legal corpus, ingestion and actual retrieval adapter. Both original worktrees were inventoried and their code preserved. The [baseline inventory](docs/plans/backend-baseline-inventory.json) records their distinct versions.

- [x] Correct raw provider response parsing and runtime-validate outputs. Eight regression cases reproduced failure before the fix. The suite exercises raw HTTP refusals, incomplete results, schema and tool validation, and asynchronous continuation.
- [x] Connect real legal corpus retrieval and case context in the local resumable journey.
- [ ] Qualify hosted semantic inference and bounded live official-source research.
- [x] Preserve tool continuations, citations, independent review, targeted repair and case-write authorization. Verified using a delayed provider, synthetic passages and the existing case commit and authorization functions.
- [ ] Evaluate realistic prototype scenarios for support, completeness and uncertainty.

### 4. Supabase backend

- [x] Implement transactional task admission and a durable outbox/queue. PGlite migration and admission/retry tests passed.
- [x] Refactor generation, tools, review and repair into checkpointed steps. Each simulated sweep advanced one durable step.
- [x] Implement asynchronous submission, collection and cancellation. Raw wire fixtures passed. Provider compatibility, account retention and BYOK remain live integration gates.
- [x] Add HMAC completion verification, duplicate wake handling and bounded scheduled recovery. Signature and SQL receipt recovery tested locally. Cron is prepared for hosted verification.
- [x] Test leases, stale-worker fencing, retry deduplication, cancellation and private event replay. The over-200-second virtual-clock test published once and withheld a claim with invented evidence.
- [x] Connect Android turn admission, progress, result, recovery and cancellation through the current transport. Frontend build passed. Device verification remains open.
- [x] Disable fake Google operation receipts at the backend boundary. Authorized requests to unimplemented operations explicitly report unavailable. Real Google integration remains in its own workstream.
- [ ] Reconcile migration history and verify hosted behavior in the correct project.

See the [backend handoff](docs/plans/backend-resumable-local-handoff.md) for exact checks, remaining limitations and rollout instructions.

### 5. Case, evidence and action workflow

- [ ] Connect facts, evidence, timeline, legal basis, drafts, communications and next actions to private cases.
- [ ] Correct Hindi rendering, export pagination and PDF page selection; validate extraction/OCR limits.
- [ ] Bind each external write approval to the exact proposed payload.
- [ ] Distinguish email sent, official submission, response received and confirmed remedy.

### 6. Google-only onboarding and Android

- [ ] Welcome screen has one account method: **Continue with Google**.
- [ ] First sign-in creates the private account; later sign-in restores it without duplication.
- [ ] Confirm available name/email and language. Date of birth is not assumed to come from ordinary sign-in; provide manual entry if collected. Exact required age/profile fields remain a product decision.
- [ ] Offer separate optional cards for Drive, Gmail send, Gmail read, Calendar and location.
- [ ] Request actual service authorization and inspect granted scopes; never infer connection from entered email or a switch alone.
- [ ] Treat location as Android permission, with manual region fallback; it is not Google Maps account OAuth.
- [ ] Show a truthful connection summary, then the three-action home. Returning users with a valid session go directly to Home.
- [ ] Denial/revocation disables the affected feature while preserving ordinary signed-in assistance.
- [ ] Verify secure storage, sign-out, cold-start OAuth return, app restart, back navigation and native sharing on a device.
- [ ] Handle any existing guest data through an explicit tested ownership-preserving path; do not silently discard or merge records.

### 7. Quality and security

- [ ] Add regressions for every defect in the implementation review.
- [ ] Test real provider response shapes, unavailable integrations and forged success claims.
- [ ] Verify two-user isolation for cases, jobs, evidence, tokens, events and approvals.
- [ ] Measure latency and evaluate representative answers against the existing backend.
- [ ] Verify language, document and accessibility behavior on actual devices.

### 8. Deployment and operations

- [ ] Configure secrets, telemetry, per-user budgets and service quotas without exposing secrets in the APK.
- [ ] Record migrations/function deployment receipts and rollback procedures.
- [ ] Compile/sign/install the Android build; verify the final configured environment.
- [ ] Record which features are accepted for the recruiter demo and which remain unavailable.

## C. Parallel work and integration

**Assigned split:** Antigravity owns the initial legal corpus/retrieval component; the **Backend & Agent Integration** Codex chat owns resumable execution and the agent transport/verification refactor. Onboarding UI and individual Google adapters remain available for separate allocation once contracts are agreed. Assignments are recorded; this coordinating chat has not dispatched either executor.

Ready-to-use task briefs: [Antigravity: legal knowledge and retrieval](docs/plans/legal-knowledge-task.md) and [Codex chat: backend and agent integration](docs/plans/backend-agent-task.md).

Before parallel implementation, agree on:

| Boundary | Shared contract |
|---|---|
| Retrieval | Query, case region/date, evidence passages, stable IDs, exact locator, source URL, version/review status, limitations |
| Agent jobs | Accepted run, persisted stage, cancellation, failure, approved result and ordered events |
| Identity | Verified user ownership, session lifecycle and ownership-preserving legacy-data handling |
| Google tools | Typed inputs/results, granted capabilities, explicit unavailable/error states and provider receipts |
| External writes | Exact approval payload/hash, atomic reservation, dispatch outcome and reconciliation |

- [ ] Commit compatible sample fixtures and boundary tests so each component can be built independently.
- [ ] Give each task its own branch/worktree and explicit file ownership. Coordinate edits to shared contracts, migrations and frontend API files.
- [ ] Preserve both existing uncommitted worktrees; inventory and reconcile them before integration. An uncommitted component cannot be integrated by simply merging its branch name.
- [ ] Integrate small working slices regularly, run contract checks, then verify real providers. Do not wait until all components are individually declared finished.
- [ ] Mark simulated tools clearly and keep them out of production success paths.

## D. Prototype milestones and acceptance evidence

- [ ] **M1 — Account entry:** Google-only sign-in, profile confirmation, optional connection cards, permission-denial behavior, sign-out and session restore work. A card without a functioning adapter shows unavailable, not connected.
- [ ] **M2 — Reliable answer:** reviewed initial legal pack + real retrieval + resumable agent + current UI produce one source-grounded answer, including a task exceeding 200 seconds overall and app reconnection.
- [ ] **M3 — Complete complaint:** evidence, editable draft, approved provider action and actual receipt work together. Calendar and location features have their own real integration checks.
- [ ] **M4 — Recruiter build:** installed Android build, hosted isolation/recovery checks, representative quality results, usage controls and accurate supported-feature list.

M1 identity work and the legal pack can progress alongside backend orchestration. M2 does not require enabling every optional Google service. No milestone permits false success or unreviewed legal publication.

For every completed implementation checkbox, record **owner, date, tested environment, evidence and remaining limitations**. Reopen it when a later change breaks its acceptance gate. Do not mark a whole workstream complete from mock tests alone.

Supporting documents:

- [Resumable agent architecture](docs/plans/supabase-resumable-agent-architecture-2026-11-20.md)
- [Google services setup](docs/plans/google-services-setup-2026-11-20.md)
- [Implementation defects and acceptance corrections](docs/plans/agy-implementation-review-2026-11-20.md)
- [Original product blueprint](docs/plans/product-blueprint-reference.md)

## Earlier engineering brief

The detail below was originally prepared on 19 November 2026. Starting-state observations are historical. The checklist and later architecture/review documents above govern newer scope and acceptance decisions.

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
9. Updated Android onboarding decision: offer **Continue with Google** as the sole account method; confirm profile, offer optional Drive/Gmail/Calendar/location setup, then enter Home. This supersedes earlier guest-first onboarding as a product target. Preserve existing guest-owned records through a tested migration path where needed; do not change the protected web demo.

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

- Supabase Auth identifies every user. Android's updated product target uses Google-only sign-in; preserve existing guest-owned records through an explicit tested path where needed, without moving another user's records. Use secure native storage for refresh credentials and other persistent secrets.
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
| **1. Auth and durable cases** | Configure Google-only Android onboarding, profile confirmation, optional integration setup, secure session storage, tested legacy-account preservation where needed, case/chat APIs and transactional request lifecycle. Extend schema/RLS and protect editorial roles. | Two users cannot read or modify each other's records, link documents across owners, forge assistant/review/approval rows, or reuse a request ID with a different payload. New chat can reopen the same case. Worker restart/version conflict and onboarding checks pass. |
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
