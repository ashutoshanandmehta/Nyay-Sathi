# Nyay Sathi V1 verification audit

Verified on 7 November 2026 (Asia/Kolkata). Scope: verify the two supplied briefs against the available implementation and prepare V2; no application implementation was requested in this turn.

## 1. Verdict

The redesign is justified, with qualifications. Preserve the React frontend, API, ownership controls, persistence, document handling, citation identity and useful regression tests. Replace the fixed intelligence orchestration gradually with one primary tool-using agent. Do not assume that every graph node incurs a model call or that the latest application is still purely keyword-routed.

The existing folder already contains an internal `request-v2` / `answer-units-v2` pipeline. It is a newer implementation inside the V1 application, distinct from the empty `/Users/ashutoshanand/Downloads/Nyay Sathi V2` workspace. Its improvements must be retained or evaluated before replacement.

Verified software checks do not establish legal correctness. Saved live reports establish behavior of those recorded runs; they do not prove the latest files reproduce it.

## 2. Evidence and checks performed

| Check | Result | Qualification |
|---|---|---|
| Backend suite, freshly executed | 534 passed; 5 dependency deprecation warnings; pytest reported 7.71 seconds | Offline, network guard in tests; real OpenAI key disabled; temporary database/checkpoint/upload/export paths |
| Frontend suite, freshly executed | 11 passed across 2 files | Vitest; not browser end-to-end validation |
| Production frontend build, freshly executed | TypeScript and Vite passed | Bundle output directed to temporary audit directory |
| Installed SDK inspected | OpenAI 3.45.0; required Responses arguments and tool-call types present | Confirms installed surface, not provider/account/model availability |
| Installed stack inspected | LangChain OpenAI 1.7.4, LangGraph 1.2.19, FastAPI 0.162.0, Pydantic 2.14.2 | Versions observed locally, not recommendations to upgrade |
| Source corpus counted | 14 curated + 607 ingested = 621 passages; source register has 20 records | Register records are not equivalent to 20 complete, current legal instruments |
| Paid live evaluations | None executed in this audit | Existing saved reports were read |
| Browser E2E / live voice / OCR / full export visual QA | Not executed | Must remain explicit execution-plan gates |

Temporary checks and backend JUnit report: `/private/tmp/nyay-v2-verification-20261107/`. Frontend tests/build required approved temporary/configuration metadata writes in V1; no application source was edited. No secrets were printed or copied.

## 3. Actual request lifecycle

All file references in the sections below are relative to `/Users/ashutoshanand/Downloads/Nyay sathi`.

1. `frontend/src/App.tsx:send()` creates a request UUID and optimistic user message. `frontend/src/api.ts:streamTurn()` POSTs content, language, request ID and attachment IDs to `/api/conversations/{id}/turns/stream`, with cookies and CSRF.
2. `backend/app/api/routes.py:stream_turn()` emits progress events and invokes `_run_turn()`. `_run_turn()` checks ownership, request identity, attachment ownership and turn concurrency, loads memory/history/documents, and builds context.
3. `backend/app/services/context_builder.py:ContextBuilder.build()` supplies current IST time, reported/confirmed facts, contradictions, dispute history, recent messages and selected private document excerpts. Drafts/staged proposals are appended by the route.
4. `backend/app/graph/workflow.py:AssistantGraph.invoke()` installs model accounting and invokes the checkpointed graph in a worker thread.
5. The compiled graph runs `triage → intake → [research → assess_information → optional web_research] → plan_resolution → execute_tasks → respond → review → [revise → rereview] → verify`.
6. `triage()` calls `ContextualInterpreter.interpret()`. The default contextual interpreter uses the segmented `request-v2` schema. Conservative offline/error interpretation exists, with restricted write permission.
7. For that newer schema, `prepare_v2()` batches routine extraction with generation; early semantic extraction remains conditional. Local retrieval is requested for consumer research tasks. The newer `assess_information()` is a deterministic candidate-presence check, not an additional evidence-sufficiency model call.
8. `execute_tasks()` chooses cached consumer evidence or calls `TaskResearchService.run()` for public research, task by task. Search and subsequent source fetches are synchronous within that execution path.
9. `UnitPipeline.generate()` generates claims, deliverables and proposed case patches in a batch. `UnitPipeline.review()` independently reviews the batch. `UnitVerifier` and `VerifiedComposer` enforce claim identity, provenance, applicability and publication policy. One repair/re-review pair is conditional on defects and remaining budget.
10. The newer route uses `TurnPersistence` and `CaseStateManager` for reviewed-result persistence, version conflicts, patch audit and replay-safe completion. It returns the existing turn contract. Legacy handling remains in the same codebase.
11. The stream emits a final `result`. The frontend then reloads conversation detail. It currently displays progress while waiting, rather than displaying incremental answer text.

## 4. Findings, with causes and limits

### A. There is a fixed model-call floor, but fewer calls than the diagram alone suggests

`ContextualInterpreter.interpret()`, `UnitPipeline.generate()` and `UnitPipeline.review()` create a normal configured path of three model calls before search, optional early extraction or repair. The independent review is unconditional for generated units; it is not risk-adaptive. `UnitVerifier.verify()` requires a fresh independent semantic verdict for claims.

Default configuration allows eight non-embedding model operations per turn. Query embeddings have a separate allowance in `services/model_calls.py`. Web discovery uses a paid OpenAI Responses request through `OfficialSearchProvider.search_public()`; it is not a free local tool. One repair adds generation and independent re-review calls. These counts are conditional, not claims that every request consumes the maximum.

### B. General research already exists; narrow consumer assumptions remain in the supported workflow

`routing/research.py:TaskResearchService` accepts validated public queries and public HTTPS sources. `routing/interpretation.py` uses contextual interpretation and includes employment-first fallback rules. Unknown organizations are not inherently rejected by an alias list.

However, `graph/workflow.py:prepare_v2()` gates local retrieval on consumer domain. `rag/retrieval.py:rewrite_query()` appends Consumer Protection Act language. `routing/task_context.py:TaskContext` grants the saved consumer corpus only to consumer tasks. `prompts/v2/units.md` explicitly calls consumer disputes the deeply supported workflow; other domains receive bounded research/preparation. V2 needs general research without allowing consumer evidence to leak into unrelated legal propositions.

### C. Research has useful safeguards but limited concurrency and ranking

`TaskResearchService.run()` loops over candidate fetches; `AssistantGraph.execute_tasks()` loops over tasks. Independent work therefore waits sequentially. Defaults are two query operations and three fetched documents. Passage ranking is query-term overlap, and initial source fetch order is provider order. It does not implement the proposed combined authority/relevance/jurisdiction/current-law ranking.

The fetcher preserves extracted text, URL, content hash and retrieval time; snippets are not promoted to supporting passages. `rag/ingest.py:fetch()` validates public destinations and redirects, bounds downloads and pins a public address while preserving TLS/SNI. Reuse these controls when introducing concurrency.

`TaskResearchService` resets unknown jurisdiction/publication/effective dates to null, which is appropriately conservative. Its official-origin heuristic also accepts `.gov`, so a foreign government source can be official without being applicable Indian authority. The saved milk report demonstrates FDA material reaching an India-focused answer; official origin must be separated from jurisdiction and relevance.

### D. Source results do reach generation and review, but context can be omitted

`UnitPipeline.payload()` constructs an `EvidenceRegistry`, includes selected public passages and exposes the same evidence to review. The hypothesis that search results never reach the final model is not supported.

There is a 20,000-character evidence selection budget; private/non-public entries sort ahead of public passages. `ContextBuilder` removes older turns over its character budget; generation further reduces recent turns and can omit optional history fields over its own budget. These are verified truncation mechanisms, not proof of the cause of a particular poor answer. Instrument omitted material and protect the central question/completed actions before changing limits.

### E. Verification is substantial but expensive and not proof of legal truth

Claim-to-evidence binding, same-claim review signatures, safe partial output and staged writes are valuable. Preserve them. The mandatory reviewer and review-bound commit policy mean removing a review call requires an explicit replacement policy, especially for case changes.

Deterministic checks cannot generally decide whether a judgment entails a novel legal conclusion. Schema validity, source authenticity and two-model agreement are each insufficient. The target architecture must preserve that distinction.

### F. Emergency priority currently affects final composition, not immediate delivery

The prompts prioritize protective help and `VerifiedComposer` sorts urgent tasks first. They still pass through normal generation/review before delivery. `routes.py:stream_turn()` sends progress, not a trusted safety message. `frontend/src/api.ts:streamTurn()` consumes progress/result events and `App.tsx` refreshes the final conversation. Immediate safety guidance therefore needs both server support and a minimal frontend handler.

### G. Conversation and case state are partly separated already

The newer pipeline proposes patches, verifies authorization, stages uncertain changes and commits with version checks. Existing tests cover unrelated requests, unauthorized writes, corrections, stale drafts, failed execution, idempotency and cross-owner access. It is inaccurate to say all questions necessarily mutate an active dispute.

Storage remains one case-memory record associated with each conversation. V2 should preserve general-question history while leaving personal case memory unchanged, and avoid adding a complex multi-case UI without need. Attachment upload currently records evidence in case memory immediately; document association deserves a specific integration test.

### H. Frontend reuse is practical, with a few necessary integrations

The existing React/Vite UI implements history, languages, attachments, voice controls, sources, case workspace, journey panels, drafts and exports. Reuse the entire UI. Its workflow panel hardcodes graph node IDs; changing backend workflow JSON alone will break it. Source-status labels and speech eligibility also depend on current verification fields. These are concrete compatibility tasks, not reasons to redesign the interface.

### I. API migration is feasible but account compatibility is unverified

Current code already uses Responses for web discovery and LangChain structured generation for interpretation/answers/review. Installed SDK introspection confirms Responses has `tools`, `tool_choice`, `input`, `text`, `reasoning`, `store`, `include`, and `max_tool_calls`.

Official [function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling) confirms the model/tool-output continuation flow. One logical agent therefore need not mean one HTTP request. Official [structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs) explicitly notes that structured outputs can still contain mistakes. Official [web-search documentation](https://developers.openai.com/api/docs/guides/tools-web-search) supports domain filtering and source enumeration. None of this establishes that a specific configured model is available to this account; keep model selection configurable and verify with a bounded smoke test during execution.

### J. Reuse licensing requires a specific PDF decision

V1 declares PyMuPDF 1.26.7 as a runtime dependency. Its [maintainer documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) describes AGPL and commercial licensing. The generic existing third-party notice does not resolve which terms the intended app distribution will satisfy. Record a license decision before release; preserve extraction behind an adapter so an alternative can be evaluated if needed. This audit does not decide the application's legal obligations or authorize a license purchase.

## 5. Recorded performance and behavior

Source: `evals/reports/three-public-prompts-20261106T195426Z.md` and its summary JSON. These are recorded V1 results, not live tests performed on 7 November.

| Scenario | Recorded total latency | Generation/search calls | Separate embedding calls | Sum of reported tokens, including embeddings |
|---|---:|---:|---:|---:|
| Amazon two fans | 79.557 s | 3 | 1 | 26,815 |
| Blinkit expired milk | 67.148 s | 4 | 1 | 41,224 |
| Employment unpaid salary | 78.974 s | 4 | 0 | 31,100 |

For Amazon, recorded provider request durations were 20.269 s interpretation, 0.869 s embedding, 37.847 s generation, and 20.206 s review. They total 79.191 s, close to recorded request time. That run supports sequential model latency as a major bottleneck; it does not establish a distribution or production percentile.

The Amazon answer recommended another written support follow-up despite reported support closure and grievance redirection. Later source files and offline tests explicitly address this behavior (`test_stage_aware_read_only_plan_does_not_restart_exhausted_support`, for example). Treat the saved output as a historical regression fixture, not evidence that the latest fix failed live.

The latest offline suite passes, but mocks do not establish real model reasoning quality. No before/after V2 latency, price, legal-accuracy score or model comparison has yet been measured. Token totals are observed usage, not monetary cost.

## 6. External source-access checks

The [NCH homepage](https://consumerhelpline.gov.in/public/) yielded usable official procedure text. [NALSA](https://nalsa.gov.in/) yielded usable navigation and legal-aid resources. [e-Jagriti](https://e-jagriti.gov.in/) returned a JavaScript application shell rather than readable instructions. The India Code BNSS detail-page fetch timed out in this audit. These outcomes justify alternate official documents and honest extraction-failure handling; they do not establish complete portal workflows or current legal applicability. No emergency contact table or scenario-specific legal answer was certified here.

## 7. Changes needed to the supplied proposal

1. Replace the primary orchestration, not every reusable module.
2. Count all provider calls, including search-generation and embeddings; do not promise one paid request per researched answer.
3. Use deterministic checks for identity, provenance, limits and known templates; retain semantic review for consequential novel interpretations.
4. Add immediate safety delivery through the existing frontend, without streaming unchecked legal conclusions.
5. Preserve staged case writes and recovery receipts when making review adaptive.
6. Treat legal freshness, source authority, jurisdiction, and subsequent judgment treatment as distinct evidence attributes.
7. Gate releases on measured quality and cost; do not treat the architecture diagram as proof of improvement.

Detailed implementation sequence: [V2_EXECUTION_PLAN.md](V2_EXECUTION_PLAN.md).
