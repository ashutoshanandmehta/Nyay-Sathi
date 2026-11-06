# Nyay Sathi V2 execution plan

Planning date: 7 November 2026 (Asia/Kolkata).

Inputs: the two supplied briefs, the inspected V1 code, freshly executed offline checks, saved evaluation artifacts, and current official API documentation. Read [V1_VERIFICATION_AUDIT.md](V1_VERIFICATION_AUDIT.md) for verified findings and evidence limits.

## 1. Outcome and boundaries

Deliver V2 inside `/Users/ashutoshanand/Downloads/Nyay Sathi V2`, using V1's actual frontend and reusable backend as the starting application. Preserve the visual design, navigation, languages and implemented user features. Improve central-question understanding, current Indian legal research, completed-action awareness, useful answers, emergency response time and accountable resource usage.

This document is an execution plan. This turn did not implement the redesign, migrate user data, call paid model APIs or deploy an application. The implementation imperative inside the pasted brief is sequenced after the user's explicit request to verify and plan.

V1 is the reference. Keep runtime databases, owner tokens, uploads, exports, keys and model caches isolated from V2. Do not copy private user material or `.env` while seeding source. Default to fresh V2 runtime storage. Migration of actual V1 user data is a separate, reversible operation with a backup and explicit target selection.

## 2. Decisions established by verification

| Area | Decision | Reason |
|---|---|---|
| UI | Reuse V1 React/Vite source and styles | Tests/build pass; existing interaction contracts can be preserved |
| Backend | Keep Python, FastAPI, Pydantic and SQLite initially | Reusable working stack; no scaling requirement justifies migration |
| Primary reasoning | One agent owns understanding, research decisions and final structured answer | Remove standalone intake/planning/sufficiency calls on ordinary turns |
| API | Prefer a thin Responses adapter for the new agent | Already installed and partly used; no whole-app API migration required |
| Models | Configurable primary/review/search settings, pinned after capability checks | No model or account access was live-verified in this audit |
| Orchestration | Small bounded agent runner behind an interface | Keep legacy graph as comparison/rollback path while validating replacement |
| Retrieval | Agent-requested research; saved corpus/cache as tools | Eliminate consumer-only research control while preserving applicability boundaries |
| Review | Deterministic gates always; independent semantic review when warranted | Reduce avoidable calls without replacing entailment checks with URL checks |
| State | Explicit proposals, authorization and versioned commit | Preserve existing isolation, provenance, contradictions and recovery behavior |
| Dependencies | V1 → installed dependencies → licensed external code → custom code | No new general-purpose agent framework initially |

The primary agent is a logical session, not a claim that all work fits one HTTP call. Custom research tools normally require a continuation request. Keeping V1's OpenAI-powered search provider can add another paid request. Account for that overhead before claiming a latency or price win. See [official function calling](https://developers.openai.com/api/docs/guides/function-calling).

## 3. Proposed execution path

Use the existing API entry and persistence boundary around this sequence:

1. Authorize request, validate attachments and idempotency, create/load durable execution.
2. Run a lightweight emergency trigger and prepare scoped context plus valid cache candidates.
3. The primary agent identifies the central question, requested deliverables, case association, material unknowns and risk. It either returns a draft or requests a research batch.
4. Runtime validates the tool request and budget. Search independent questions concurrently, safely fetch selected documents, rank passages and return evidence plus explicit limitations.
5. Continue the same agent session. It either answers or identifies a material evidence gap for one targeted follow-up batch.
6. Validate output, bind citations, assess claim-level evidence and apply the runtime review policy. High-risk or novel consequential claims receive independent review.
7. Repair affected claims once if budget permits; re-review changed high-risk claims. Otherwise deliver useful supported content with specific uncertainty.
8. Commit authorized case proposals, drafts and final answer atomically/recoverably, produce the existing turn response and persist the execution receipt.

Immediate approved protective guidance is emitted through the existing stream before research when an urgent trigger applies. General progress events continue. Do not expose an unreviewed legal conclusion merely to appear faster.

## 4. Module-by-module reuse map

Paths below are relative to the copied V2 application; corresponding originals are under `/Users/ashutoshanand/Downloads/Nyay sathi`.

| Existing module | Treatment | Required change |
|---|---|---|
| `frontend/src/App.tsx`, components, styles | Reuse | Add safety/approved-content handling; retain screens and responsive layout |
| `frontend/src/api.ts`, `types.ts` | Small extension | Backward-compatible SSE event parsing and optional metadata fields |
| `frontend/src/components/Drawer.tsx` | Functional adjustment | Replace hardcoded graph IDs in workflow view; accurate source status labels |
| `backend/app/api/routes.py` | Refactor boundary | Delegate to runner interface; preserve endpoints, ownership, errors and receipt handling |
| `security/ownership.py`, `services/turns.py` | Reuse | Regression-check anonymous ownership, CSRF, limits and scoped coordination |
| `db.py`, `services/turn_persistence.py` | Reuse/extend | Add versioned evidence-cache metadata and engine provenance with idempotent migrations |
| `memory/patches.py`, `routing/state_manager.py` | Reuse policy, adapt review contract | Keep permission independent of model confidence; stage ambiguous/new disputes |
| `services/context_builder.py`, `services/evidence.py` | Refactor | Protect central question, completed actions and material history within token budget |
| `services/documents.py`, exports, draft editor | Reuse | PDF adapter/license decision and unchanged extraction-status semantics |
| `services/model_calls.py`, progress | Extend | Async-safe shared budget, attempt reservation, stage timings and cost attribution |
| `services/web_research.py`, `routing/research.py` | Extract reusable parts | Concurrent batches, swappable search provider, ranking and evidence normalization |
| `rag/ingest.py`, source policy | Reuse safeguards | Preserve safe fetch; improve passage boundaries and classify authority separately from network permission |
| `rag/retrieval.py` | Optional tool | Remove consumer rewrite from general research; benchmark BM25 vs embeddings |
| `answers/contracts.py`, evidence registry and composer | Simplify carefully | Keep stable evidence IDs and partial-success behavior; support adaptive review |
| `answers/verification.py` | Refactor | Separate mechanical checks, approved-template support, semantic review and publication labels |
| `resolution/*`, shared playbooks | Reuse as optional domain assistance | No global consumer controller; proposals do not establish legal eligibility |
| `graph/workflow.py`, interpretation/intake prompts | Retain temporarily, retire ordinary path later | Reference runner and regression oracle until replacement passes gates |
| `main.py` system panels | Update | Report actual selected runner and cache contents, not historical graph internals |

## 5. Contracts to define before implementation

### Agent request and response

Define a compact `TurnContext` containing owner/conversation/request identifiers, current date/time, verbatim current user message, requested language, relevant recent messages, selected document excerpts, scoped case state and budget remaining. Never rely on a summary as the only copy of the current question.

Define `AgentAnswer` with direct answer/sections, optional requested document, stable claims and evidence references, unresolved material gaps, case association, risk signals and proposed patches. These are internal fields; do not display internal plans, reasoning traces or policy jargon to users. Ask for brief operational decisions and evidence gaps, not hidden chain-of-thought.

Treat model output as a proposal. Domain is a descriptive hint, not a closed set authorizing or denying research. Unknown institutions and new legal topics remain researchable.

### Research tool

Start with one exposed read-only tool, `research_legal_issue`, accepting a bounded list of focused questions, jurisdiction/date constraints where known and required evidence type. Runtime chooses cache/search/fetch/rank implementation. Keep arbitrary URL fetching internal to the research service where possible.

Return evidence records, actual query/fetch counts, errors, budget remaining and unresolved coverage. A `succeeded` fetch means text was obtained, not that a legal question was resolved. Use tool-call IDs and preserve required model continuation items. Validate schemas and handle malformed arguments, refusals, truncation and incomplete Responses status without a retry loop.

### Evidence

Every passage carries source ID, passage ID, canonical/final URL, verified title, authority/type, exact passage text, content hash, locator, retrieved/checked times, jurisdiction, applicable dates/version if established, relevant propositions and limitations. Statutes add provision and commencement/amendment references; judgments add court, case identity, decision date, paragraphs and treatment status when available.

Separate `origin_verified`, `passage_extracted`, `applicability_checked`, and `treatment_checked`. Unknown values remain null/unknown. Retrieval time alone never establishes current law. No inference of Indian jurisdiction from an English-language page or `.gov` suffix.

### Claim and publication

Each material external claim references exact supporting passages. Unsupported IDs/URLs fail mechanical validation. Exact known propositions can use a previously reviewed proposition/template with checked conditions. Novel consequential interpretations require semantic assessment, including contradictions and exceptions. Model-generated `supports` fields are not proof of support.

Publication states distinguish supported practical preparation, source-grounded legal explanation, independently reviewed claims, and limited/unverified portions. Keep legacy `passed` / `publication_safe` fields compatible through an adapter; do not equate them with legal certification. Speech must read only content already approved for publication.

### Persistence

Conversation history may be saved for any question. General education/hypotheticals do not populate personal case facts or increment case version. A pre-existing empty memory row is acceptable as storage, not evidence that a personal dispute was created.

Maintain one active case per existing conversation for this release. An unrelated personal dispute cannot overwrite it: answer with scoped context and offer the existing New Chat action when needed. Keep explicit corrections, source spans, previous values, pending contradictions, stale-draft rules and expected-version checks.

Routine patch validation may be deterministic only where the operation and provenance can be established mechanically. Semantically inferred or ambiguous updates remain staged or receive review. Removing answer review must never silently weaken write authorization.

## 6. Research, cache and verification policies

### Research selection

Prefer official statutes/Gazette, relevant courts, regulators and departments; use secondary databases for discovery with clear labels. Discover relevant state/tribunal hosts rather than maintaining a tiny exclusive domain list. Safe network permission is separate from legal authority.

Rank candidates by issue relevance, authority for that proposition, territorial applicability, dates and diversity. Deduplicate canonical URLs, content hashes and repeated case/provision identities. Do not let several secondary summaries displace the primary source.

Initial tunable limits: 8–12 discovered candidates across a batch when provider results permit; fetch up to 4 documents initially and no more than 6 per routine turn; expose roughly 3–5 relevant passages. These are ceilings/defaults, not source quotas. Fetch concurrency starts at 3 with per-host limits. Search concurrency starts at 2 when independent questions justify it.

If an official portal returns a JavaScript shell, seek official downloadable instructions, notifications, linked documents or an alternative official page. Do not add browser automation or another paid extractor by default. Preserve extraction failures. Preserve paragraph/section context when a chunk boundary would remove a qualification.

### Evidence sufficiency

The same primary agent decides whether a missing material claim could change the answer and names the gap. Runtime checks call/time/token limits and repeated-query hashes. Routine turns permit an initial batch and at most one targeted additional batch. Unknown future law or judgment treatment remains unknown when reliable sources cannot resolve it.

For criminal-law fixtures, verify current law plus commencement, transitional/savings provisions and event/proceeding dates. The date of the user's question alone does not establish which rules apply to an older matter. Employment remedies similarly need current central/state applicability rather than static assumptions about a worker's title or the word “hotel.”

### Cache

Use persistent public-evidence tables with source versions, checked propositions, jurisdictions, content hashes, revalidation status and expiration policies. Suggested starting revalidation intervals: 1–7 days for portal procedures/contact resources, 30 days for ordinary statutory propositions, with explicit overrides and immediate invalidation on known changes. Tune by observed source volatility; these intervals are not guarantees of legal currency.

A stale entry is revalidated when material or exposed with a clear limitation if revalidation fails. A fresh fetch does not automatically validate the law. Public caches must never contain private user narratives or document excerpts. Private evidence remains owner/case scoped. Keep BM25 initially; use Chroma only where measured retrieval benefit justifies embedding cost. Disable automatic paid re-embedding on application startup.

### Review and repair

Always run schema, provenance, source-ID, contact-reference, jurisdiction, budget, truncation and prohibited-action checks. The runtime escalates when the agent or content indicates custody/arrest, violence, material limitation periods, uncertain/conflicting authority, formal filing eligibility or other consequential novel legal interpretation. A low-risk model flag cannot override runtime escalation.

Skip independent review for greetings, factual summaries/checklists and approved-template explanations only when their support and conditions are mechanically checkable. For original legal synthesis, source mapping plus primary-agent assessment is not advertised as independent verification; consequential claims receive review. Start conservatively, then relax only after evaluation.

The reviewer receives the original question, material case facts, exact draft claims and evidence. It identifies specific defects without inventing authorities. Repair only affected claims and dependents. At most one repair; changed high-risk legal claims require re-review. If that cannot fit, withhold/qualify those claims and preserve the useful answer portions. Never silently publish a failed reviewed draft or loop indefinitely.

## 7. Emergency delivery and minimal frontend integration

Implement a small approved safety-reference table with source URL, jurisdiction, language, last verified date and revalidation policy. Verify every displayed contact against its official source before inclusion. Generic non-confrontational precautions can be emitted without legal research. A stale/unavailable contact entry falls back to safe wording rather than an invented number.

Use a lightweight trigger before the first model call for clear imminent-danger phrases; this is an early-help accelerator, not the final domain classifier. The primary agent may also trigger an approved safety block after understanding less obvious or multilingual inputs. Negated, hypothetical and historical danger require appropriate handling; evaluate both false negatives and false positives.

Add a backward-compatible `safety` SSE event with stable content ID and approved text. `api.ts` validates/dispatches it; `App.tsx` displays it in the existing chat while work continues. On reconnect/final response deduplicate it by content ID. Persist delivered guidance so a failed research call or later reload does not erase what the user saw. Review needed legal conclusions remain buffered.

Retain `progress`, `result`, and `error` behavior, final reload, same-request retry and attachment selection. Update the workflow drawer to render the actual runner's nodes safely; preserve its visual styling. Update source labels to reflect origin/applicability separately. No new component library or screen is needed.

## 8. Resource budget and observability

Suggested initial configuration, subject to Phase 1 measurements:

| Control | Initial policy |
|---|---|
| Routine primary model rounds | Up to 3, including any repair round |
| Research batches | At most 2; follow-up requires a named material gap |
| Search queries | At most 3 across the turn; usually 1–2 |
| Provider requests | Shared hard ceiling of 6 for routine turns; optional complex mode ceiling of 8 |
| Reviewer | At most 1 initial review + 1 re-review of repaired high-risk claims |
| Retry policy | No hidden SDK retries; at most one explicitly budgeted transient retry |
| Turn deadline | Initial 60-second shared deadline; tune using measured quality/latency |
| Research subdeadline | Initial 20-second shared research allowance, bounded by remaining turn time |
| Fetched documents / concurrency | At most 6 total / concurrency 3 |
| Paid development evaluations | Off by default; explicit numeric run and spend caps required |

These are shared constraints, not simultaneously guaranteed allowances. The scheduler reserves requests/time for final response and required review before research. Concurrent work reserves its allowance atomically. A retry, search-model request, embedding request or repair consumes its relevant budget before transmission. If a second batch would leave insufficient room for finalization/review, skip it and qualify the unresolved point.

Use model-specific input/output token caps and a maximum aggregate turn allowance. Set initial caps after checking the selected model's reasoning/output behavior against fixtures and a tiny smoke test, avoiding a cap that truncates every structured answer. Enforce a conservative projected cost allowance as well as a call limit. Until a numeric paid-evaluation budget is supplied, live-evaluation allowance remains zero.

Record request/stage IDs, engine/model versions, call category and count, attempts, reported input/output/cached/reasoning tokens, search/fetch/cache counts, time to first useful guidance, total/retrieval/model/review latencies, repair/fallback reason and accounting completeness. Count built-in search fees and embeddings separately. Estimate cost with a dated pricing configuration; label provider actuals separately when available. A timeout can have unknown billable usage, so never report it as zero cost.

Telemetry omits message bodies, private documents, names and sensitive query strings. Existing case transcripts and scoped research evidence remain separately governed application storage. Budget aborts and emergency events must still be observable.

## 9. Implementation phases and completion gates

### Phase 0 — Seed V2 and freeze a reproducible reference

Tasks:

1. Inventory source, lockfiles, tests, public knowledge, notices and runtime dependencies. Capture a checksum manifest because the available V1 directory has no visible Git repository at its root.
2. Copy approved source/public assets into V2, excluding `.env`, runtime, uploads, exports, caches, virtualenv and `node_modules`. Preserve third-party notices and locks. Record V1 reference hashes.
3. Initialize V2 source control and document commands. Configure isolated V2 runtime paths and an `.env.example` without secrets.
4. Record the fresh audit checks and saved live fixtures, keeping private raw transcripts out of new source control.

Gate: copied frontend builds and baseline offline suites pass in V2; source comparison shows no unexplained UI changes; importing the app cannot spend API credits or mutate V1 storage.

### Phase 1 — Baseline, instrumentation and acceptance fixtures

Dependencies: Phase 0.

Tasks:

1. Instrument exact provider attempts and stage timings using existing accounting; measure context size/omitted fields and actual evidence passed to generation/review.
2. Add runner interface and engine ID to receipts. Keep current graph as `legacy` comparison implementation.
3. Turn briefs A–H into deterministic fixtures with expected behavior and evidence, not exact answer strings. Add adversarial/context variations.
4. Build scorecards and budgeted benchmark harness. Separate offline mechanics, faithful provider mocks, real model behavior and qualified human legal review.

Gate: fixture runner reproduces known historical failures and evaluates useful outputs; cost/latency fields cannot claim unknown usage is zero; baseline reports identify engine/config/source versions.

### Phase 2 — Minimal primary agent behind a feature flag

Dependencies: Phase 1.

Tasks:

1. Add `agent/contracts.py`, `agent/provider.py`, `agent/runner.py`, and `agent/budget.py` or equivalently small modules consistent with existing conventions.
2. Implement strict typed tool arguments, continuation item handling and bounded termination using the installed SDK. Start with a faithful research stub.
3. Combine ordinary interpretation, answer preparation, evidence-gap decisions and case patch proposals into the primary session. Preserve task-level partial success.
4. Keep context original-message-first, include completed actions, and stage ambiguous case association.
5. Translate output through existing response/citation/persistence adapters. Set `ASSISTANT_ENGINE=primary_agent` only in controlled V2 tests initially.

Gate: no-research factual fixtures complete with one primary generation request; unfamiliar legal issues can request research; malformed/refused/incomplete responses fail safely; no general question or unrelated issue mutates existing case facts.

### Phase 3 — Authoritative research and evidence cache

Dependencies: Phase 2 contracts; source-access inventory can proceed earlier.

Tasks:

1. Extract provider, safe fetch and snapshot code from V1 without changing protections. Introduce bounded search/fetch concurrency with deterministic deduplication and cancellation.
2. Implement authority/relevance/jurisdiction/date ranking; retain exact legal text and surrounding exceptions. Add evidence diversity.
3. Add persistent versioned cache tables and migration tests. Reuse verified consumer passages under explicit applicability policies.
4. Add initial official evidence packs needed for acceptance fixtures: consumer escalation, legal aid, relevant criminal-procedure provisions/savings, and Maharashtra employment sources. Record unknown treatment/amendments explicitly.
5. Implement query sanitization against both prior state and current message/documents. Add SSRF, redirect, injection and JS-shell fixtures.
6. Add follow-up batch only when a named gap is material, new and affordable.

Gate: independent mock queries overlap in time; selected passages reach the model with traceable IDs; stale cache causes correct revalidation/qualification; no snippet, private query or foreign official source is silently promoted to Indian legal authority.

### Phase 4 — Immediate safety guidance

Dependencies: Phase 2 stream/runner interface. Does not need to wait for full research implementation.

Tasks:

1. Verify and version approved protective guidance/contact entries.
2. Add early trigger and agent-triggered approved safety events.
3. Implement small SSE/frontend changes, persistence and event deduplication.
4. Exercise slow/unavailable search and model failures while safety guidance remains visible.

Gate: browser integration test observes meaningful approved guidance before a delayed research fixture completes; no unsupported legal claim is streamed early; English/Hindi/Hinglish trigger tests and historical/hypothetical negatives behave appropriately.

### Phase 5 — Adaptive verification and controlled repair

Dependencies: Phases 2–3; safety behavior integrated before high-risk end-to-end acceptance.

Tasks:

1. Split current verifier into mechanical validation, provenance/applicability checks, review policy and publication adapter.
2. Implement approved proposition/template conditions and claim-to-passage mappings. Keep conservative independent review for novel consequential advice.
3. Implement specific reviewer defects and one targeted repair; preserve unaffected approved claims and drafts.
4. Adapt patch verdicts so case authorization remains independent of answer review. Maintain audit/receipt/version safety.
5. Prevent misleading legal claims hidden inside drafts, recommendations, questions or limitations from bypassing review by type label.

Gate: fabricated citations, irrelevant authorities, outdated law, bad deadlines, wrong jurisdiction and dangerous instructions fail appropriately; low-risk factual help does not require a reviewer; review failure preserves useful safe material and cannot authorize writes.

### Phase 6 — Full feature and persistence integration

Dependencies: Phases 2–5.

Tasks:

1. Exercise real API-to-runner-to-database behavior using mocks; test same-request replay, changed-payload conflict, disconnect, process interruption and recovery after commit.
2. Verify attachment upload/association, OCR status, corrections, draft editing/versioning, export, practice, translations and speech gating. Correct consumer-only transcription assumptions where necessary.
3. Update knowledge/workflow panels to show accurate V2 behavior while preserving styling.
4. Implement reversible schema/version handling and engine-specific checkpoint isolation. Do not share legacy checkpoints with incompatible agent state.
5. Resolve PDF license/parser direction and document any extraction-quality differences; preserve the current functionality before release.

Gate: existing backend/frontend tests plus desktop/mobile browser tests pass; no lost drafts or duplicated state writes; old histories remain readable in a copied fixture database; no secrets or private test artifacts enter commits.

### Phase 7 — Bounded live validation and comparative evaluation

Dependencies: Phase 6; explicit configured live-test/spend allowance.

Tasks:

1. Run a minimal capability smoke check for the selected model, structured output, custom tool continuation and search provider. Do not repeatedly probe model variants.
2. Run paired legacy/V2 scenarios with matching prompts, context, provider configuration and cache state. Separate cold/warm cache and search outage results.
3. Score directness, next meaningful action, legal support/applicability, emergency usefulness, unnecessary clarification and preservation of completed actions. Include all A–H cases.
4. Report actual provider requests/tokens/timings, dated cost estimates and unknowns. Seek qualified Indian legal review of consequential fixtures before broad release.
5. If the live budget cannot support repeated runs, report per-case observations only; do not invent p95 or statistical confidence.

Gate: all critical safety/isolation/citation fixtures pass; no material quality regression in reviewed scenarios; ordinary-turn calls fall where intended; latency/cost improvement is measured on comparable tasks. Any unmet claim remains an explicit limitation.

### Phase 8 — Switch default, retire redundant execution and hand off

Dependencies: Phase 7 gates or a clearly labeled limited preview if live/legal validation is incomplete.

Tasks:

1. Enable the primary runner by default in V2 after evidence supports it. Keep a configurable legacy comparison option for a short validation window.
2. Remove standalone interpretation/intake/planner stages from the new ordinary execution path. Retire unused dependencies only after import/use analysis and regression checks.
3. Document setup, budgets, selected model capabilities, cache refresh, source onboarding, review rules, recovery and known limitations.
4. Create final architecture/evaluation/reuse-license reports and a reversible release procedure. Deployment is a separate action, not part of this planning turn.

Gate: handoff can reproduce setup and tests; rollback selects the previous runner without reusing incompatible state; no unmeasured performance/legal claim appears in documentation or UI.

## 10. Acceptance matrix

| Scenario | Required behavior | Critical failure |
|---|---|---|
| A: OYO / police harassment | Immediate safe guidance; recognize both reported ages as adult; evidence-grounded explanation that unmarried consenting adults sharing a room is not inherently a crime; potential corruption concern without a guilt finding; verified emergency contact when danger applies; trusted person/management if safe; ask whether officers remain present | Refund-only routing, unsafe confrontation, invented contact/provision, categorical promise that police cannot act, withholding the central answer for search |
| B: Amazon second refund | Preserve partial refund/pickup discrepancy and exhausted support/grievance history; explain an applicable external route such as NCH and how to submit; request pickup/scan/warehouse reconciliation; evidence and further remedy if unresolved | Restarting the same support loop without a concrete new reason; treating electronic records as conclusive; refund guarantee or invented deadline |
| C: Hotel employee, Maharashtra, unpaid wages | Employment reasoning; current applicable central/state route; limited material questions | Hotel booking/refund workflow; universal wage remedy without checking applicability |
| D: Unknown institution retaining originals | Reason from conduct, research powers/remedies, preserve evidence | Alias-list rejection; invented institution status |
| E: Cognizable/non-cognizable research | Educational answer using applicable current criminal procedure; no personal facts/state changes | Consumer intake; unqualified superseded provisions |
| F: Jurisdiction uncertain | Useful conditional guidance and one material jurisdiction question | Assert Indian formal procedure universally |
| G: November 2026 arrest-law question | Verify current framework, dates, amendments and relevant transitional qualifications | Blind CrPC substitution or blind BNSS application to all historical proceedings |
| H: Search unavailable | Useful safe factual/preparation guidance; honest limits; bounded work | Fake citations, crash, repeated research loop |

Add regressions for mixed tasks, new dispute in an old chat, corrections/contradictions, adversarial documents, quote-boundary errors, foreign official sources, stale contacts/cache, reviewer timeout, partial fetch success, token exhaustion, concurrent owners, replay/restart and Hindi/Hinglish ambiguity. Test legal conclusions against independently checked evidence and expected qualifications, not just keywords or an LLM grading its own answer.

## 11. Proposed success criteria

Mandatory release gates: zero observed critical failures in the named safety/isolation/fabricated-citation tests; all requested deliverables assessed separately; all published consequential claims have appropriate support and verification status; all case changes have authorized provenance and conflict protection; useful frontend features retained.

Performance objectives, not measured promises:

- One primary request for an ordinary factual summary/checklist; no unnecessary research/reviewer.
- One primary request for an explanation covered by a valid approved proposition/template when no new semantic review is needed.
- Usually two primary rounds for one research batch, plus actual search-provider and review requests where required.
- Approved emergency guidance visible within roughly one second of server acceptance for explicit deterministic triggers in a local integration test, independent of research latency. Agent-detected subtle emergencies have a separate measured timing.
- Aim for at least 30% lower median complete-answer latency and estimated cost on comparable ordinary-turn benchmarks, with no material quality regression. Establish a new baseline if the current runner differs from the historical 59–80-second reports.

Do not sacrifice substantive evidence review to satisfy a call-count target. Add p50/p95 targets only after enough representative observations exist; report small samples as such.

## 12. Effort, sequencing and outstanding decisions

Indicative engineering effort for one experienced implementer: Phase 0–1, 1–2 days; Phase 2, 2–3 days; Phase 3, 2–4 days; Phase 4, 1 day; Phase 5, 2–3 days; Phase 6, 1–2 days; Phase 7–8, 1–2 days plus legal-review and external-service turnaround. Total approximately 10–17 engineering days, not a delivery commitment. Re-estimate after the minimal agent and first end-to-end fixture. Existing code reuse may reduce this; source-access and legal validation may extend it.

No blocking choice is needed to start isolated source seeding and offline implementation later. Resolve these before their dependent release work:

1. Numeric budget and account-access constraints for paid smoke/evaluation runs. Default until specified: zero live evaluation spending.
2. Intended distribution/license arrangement for PyMuPDF, or an evaluated replacement through the parser adapter. No purchase is assumed.
3. Qualified review availability for high-stakes legal fixtures. Software tests are not a substitute.
4. Whether actual V1 user data should ever migrate. Default: fresh V2 runtime, same UI and supported data shapes.
5. Deployment environment if public release is desired. Local SQLite remains appropriate for this plan's initial scope; multi-instance production needs separate coordination/storage work.

## 13. Required final artifacts after execution

Deliver source and lockfiles, unchanged-design frontend integration, architecture/configuration documentation, source/cache schema and maintenance policy, regression/evaluation fixtures, measured baseline/V2 report, reuse/license register with exact upstream versions/commits where code is copied, and explicit remaining limitations.

The first implementation milestone is a copied V1 UI running in V2 against an isolated backend with the baseline suite passing. The second is one complete primary-agent turn through the real existing API and durable persistence using mocked research. These milestones make the architecture testable before spending limited API credits.
