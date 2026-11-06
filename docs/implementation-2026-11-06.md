# Evidence, progress, and conversational reliability increment

## Design decisions

The application remains a modular monolith. React components own presentation; FastAPI authenticates owner/case access; LangGraph orchestrates specialists; focused services perform private evidence search, review policy, progress publication, and turn coordination. Existing SQLite persistence and source retrieval are reused. Composition is used instead of an extractor inheritance hierarchy because the three existing extractors are small functions with one shared contract. No new infrastructure or dependencies were required.

`EvidenceSearchService` is independent of HTTP, model clients, and persistence. It accepts attachments already authorised by the API and derives stable content-based chunks at page boundaries. `TurnCoordinator` owns locks keyed by owner and case. `ReviewPolicy` owns the revision budget rule and the narrow fast intake path. The request-local progress callback is injected at runtime, never through model arguments or checkpoint state.

No SQL schema migration was needed: page metadata already existed. Old attachments remain readable; chunks are derived on demand rather than introducing a second private evidence index. Corrections retain original extraction text, original page metadata, and previous text versions in private metadata. Corrected text explicitly loses its original PDF page mapping. Original uploaded bytes remain unchanged.

## Request flow

1. Check owner, case, CSRF, idempotency, and concurrency.
2. Reject attachment IDs outside the authorised case before saving the user turn.
3. Assemble current IST time, memory, history, and relevant page/span evidence excerpts.
4. Run intake, optional official-source retrieval, and candidate generation.
5. Independently review against the current user message, memory, documentary excerpts, and retrieved passages. Citation-format findings are supplied during review so revisions can repair them.
6. If two model calls remain, permit one revision and independently review it again.
7. Check citation identity, request review results, and internal-state leakage before saving/displaying the final response.

Default call budget is five: intake + generation + review + revision + re-review. The existing local configuration's call limit was updated from four to five; API credentials and model choices were untouched. A revision alone never satisfies review. Simple short intake messages skip model extraction; substantive answers still undergo independent review.

## Progress and UI

The POST SSE endpoint publishes node start/completion events during execution, including durations, and sends only the final saved answer. It does not stream candidate legal text. The browser reads UTF-8 event frames incrementally and displays friendly stage labels. Each turn resets reducer-backed event history. A dropped stream reports an interrupted connection; an in-process turn continues to persistence and can be retried using the same request ID.

The composer snapshots input, clears immediately, and restores failed input only if it would not overwrite new text. Uploading disables send. Attachment removal updates the submitted attachment list. Chat switching remounts the composer to prevent draft/attachment carryover, and retries retain their original case and language.

The case drawer renders a plain overview and collapsible facts, evidence, timeline, actions, drafts, and lawyer questions. It omits empty sections and hides raw memory summaries and UUIDs. Evidence can be previewed and corrected; corrections mark dependent drafts stale.

## Executed validation

- Backend: 112 deterministic tests passed; raw JUnit output in `evals/raw_outputs/pytest-2026-11-06.xml`.
- Frontend: 7 component tests passed; TypeScript and production build passed.
- Browser: 5 tests passed across desktop/mobile, 3 intentionally skipped project-inapplicable cases. Includes upload, ready status, immediate clearing, preview, and refresh/resume. Screenshots were visually inspected.
- Live: two synthetic cases used configured OpenAI generation/review and existing official retrieval. Invoice colour complaint passed automated review in 49.170 seconds; short refund intake passed in 8.971 seconds. Raw answers, passages, events, memory, usage, models, and findings are saved in `evals/raw_outputs/live-attachments-2026-11-06.jsonl`.

## Remaining limits

The invoice path still took 49 seconds because it used all five model calls. The planned 30% median latency reduction is not established by two non-paired runs. Stage timings now expose this cost; no latency guarantee is made. A simple refund intake used two calls and completed in approximately nine seconds.

Live evaluation passed model-based checks, not independent legal validation. Lawyer review remains pending. No new live transcription/speech test was performed. New OCR handling is covered by deterministic failure tests; scanned document quality still depends on local Tesseract and installed languages. Private search is lexical and can miss paraphrases. Preview supports extracted text, not a rendered PDF viewer. Extraction has an aggregate upload status rather than a per-page live progress channel. Connection recovery does not replay historical SSE frames; refresh loads saved messages, and same-request retries remain safe. Turn locks are local to one process; run one backend worker with SQLite. The wider repository refactor into repositories/view assemblers and a strict token-budget enforcement redesign remain further work; this increment introduced only the abstractions used by its working slice.
