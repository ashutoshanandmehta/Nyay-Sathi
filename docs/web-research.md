# Bounded official web research

Update: [independent request routing](request-routing.md) adds a separate task-research adapter for general/safety and unfamiliar legal questions. The official consumer-corpus allowlist remains intact; network fetch permission does not establish legal source trust. Interpreter/intake/response/review transport retries are now zero, and the shared budget includes interpretation. New validation results are in [the routing report](../evals/reports/request-routing-2026-11-06.md); the earlier live limitations below remain historical failures, not passing results.

## Implemented flow

Local retrieval now flows through `assess_information`. A structured `ResearchPlan` selects sufficient local evidence, missing personal information, unsupported scope, or a concrete public information gap. It must reference existing passage IDs when declaring local support sufficient. `web_research` executes only a search decision with permitted query intents and sufficient remaining budget. Greetings and ordinary factual intake continue to bypass legal retrieval.

The planner combines question assessment and query planning into one call. It sees authorised case context, but the search provider does not: `SearchQueryPolicy` accepts closed topic/angle enums and constructs neutral public queries from reviewed vocabulary. Names, amounts, order IDs, documents, arbitrary URLs, and free-form model query strings cannot enter that external input. National consumer topics are supported; state-specific routing and open-ended judgment queries are not yet represented in this vocabulary.

Components use composition and injectable collaborators: `ResearchPlanner`, `SearchQueryPolicy`, `OfficialSearchProvider`, `SafeSourceFetcher`, `EvidenceSufficiencyAssessor`, and `ResearchRepository`. Existing discovery source extraction, source ingestion parsing, LangGraph checkpoints, answer review, citation resolver, and progress streaming are reused. No new dependency or external repository code was copied.

## Sources and trust

Discovery and fetching share the exact host policy in `app/rag/source_policy.py`. Search-domain filtering is supplemented by destination validation because a search filter alone does not secure downloads. Each redirect is checked. Fetching resolves public destinations, pins the selected public IP, retains the original Host and TLS server name, disables environment proxies, and applies size/read/time limits. DNS resolution itself depends on the operating system resolver.

Only fetched HTML/PDF text enters the candidate legal passages. Snippets and generated search answers do not. Source snapshots retain canonical URL, hash, retrieval time, locator, text, and explicit applicability limitations. HTML locators contain the canonical URL so same-titled pages remain distinguishable. Unknown publication/effective dates remain null. Scanned public PDFs without readable text produce an extraction failure rather than invented content; public-source OCR is not implemented in this increment.

The deterministic relevance gate filters unrelated text; its term overlap is not a legal confidence score. The independent answer reviewer checks meaning, statute identity, conditions, exceptions and applicability. Citation formatting can be normalised before review only when an exact title/URL pair uniquely resolves to a fetched source and stored locator. Unknown or ambiguous markers remain failures. Revised answers still receive a fresh review.

## Persistence, cache, and deletion

The idempotent startup schema adds `research_sources` to SQLite. Original public bytes and extracted passages are stored under authorised case/message scope and cascade-delete with the conversation. Answer metadata separately retains the supporting excerpts for refresh/resume and source inspection. Public research is not automatically promoted into shared Chroma or the approved source register. Existing batch ingestion remains the promotion mechanism.

An eight-document, process-local cache stores only public source snapshots; its key includes URL, destination policy version, and extraction limits. Entries retain their original retrieval timestamps, expire after one hour by default, and are copied before reuse to prevent shared mutation. It caches neither personal evidence nor personalised answers. Public cache entries can remain until expiry after a case is deleted because they contain independent public material; SQLite/WAL physical-remanence limitations still apply to case records.

## Configuration and budgets

The configured OpenAI search model is preserved; the current adapter uses low reasoning effort, one explicitly requested search, `max_tool_calls=1`, no SDK retries, and `store=False`. Unexpected extra provider tool events are recorded and rejected rather than silently ignored. In the first live attempt, the provider returned a tool-limit mismatch; the constrained single-search instruction subsequently returned one search event successfully. Provider behaviour and billing must still be monitored.

- `WEB_RESEARCH_ENABLED=true`
- `WEB_MAX_QUERIES=2`, including refinement; one research expansion per turn.
- `WEB_MAX_DOCUMENTS=3`, with at most two concurrent downloads.
- `WEB_RESEARCH_TIMEOUT_SECONDS=40` for the web stage; planning and final response review are additional time.
- `WEB_MAX_DOWNLOAD_BYTES=5242880` per source, at most 15 MiB for three sources.
- `WEB_MAX_PDF_PAGES=60`
- `WEB_CACHE_TTL_SECONDS=3600` (`0` disables the public document cache).
- `MAX_MODEL_CALLS_PER_TURN=8`: up to five existing intake/answer/review calls, one planning call and two search requests. The runtime reserves four calls for generation/review/revision/re-review before starting web work. Limits below the required reservation skip web work honestly.

The existing local non-secret call-limit setting was changed from five to eight; no key or model name was changed. Model calls are logical requests; the older generation/intake SDK clients still permit their existing bounded transport retries. Search/planning clients do not retry automatically. Provider token usage is reported where available; usage for failed responses can be unavailable. Cancelling queued fetches prevents late case writes, though already-running network/DNS operations cannot be forcibly killed by a Python thread.

## Executed checks and live limitations

Deterministic tests cover query privacy, topic relevance, multiple requests, local sufficiency, personal-fact clarification, budgeting, source rejection, redirects, TLS hostname preservation, fetched-only evidence, extraction, cache isolation, snapshot reopen/deletion, citation repair, and the compiled graph's web branch with explicitly labelled doubles. Frontend/browser checks cover source presentation, updated workflow information, normal chat, desktop/mobile attachment and refresh journeys. See raw JUnit output and the final test counts in the implementation handoff.

Live evaluation spent the configured twelve-request allowance across one complete empty-corpus graph run and targeted diagnostics/follow-up checks. The full run identified the gap and generated two appropriate queries, but search tool-limit failures led to a truthful limited answer (93.726 seconds). A constrained follow-up search succeeded with one tool call. Live fetching successfully read three returned official URLs; three relevant excerpts then reached live generation and independent review (21.774 seconds). That review rejected URL-as-locator citations, so the answer was withheld. The identity-only citation normaliser and unique HTML locators were subsequently implemented and regression-tested.

There was no additional full live graph run after the final fixes because the live request allowance was exhausted. Do not describe these records as a passing live end-to-end evaluation. Raw records are in `evals/raw_outputs/live-web-research-2026-11-06.jsonl`. A further budgeted run can be performed using `cd backend && .venv/bin/python -m scripts.run_web_research_eval`. Indian lawyer review remains pending; automated review does not establish legal correctness.

## Progress checklist

- [x] Structured gap assessment and query planning.
- [x] Trusted vocabulary and shared source policy.
- [x] Bounded search, safe fetching, extraction and relevance filtering.
- [x] Persistent case-scoped source snapshots and public document cache.
- [x] Graph routing, progress labels, source inspection and review integration.
- [x] Deterministic, frontend and browser checks.
- [x] Budgeted live search/fetch/generation/review diagnostics with honest raw outputs.
- [ ] Passing full live end-to-end rerun after the final citation changes.
- [ ] Independent Indian lawyer review.
