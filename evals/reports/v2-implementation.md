# V2 implementation evaluation — 7 November 2026

## Executed verification

| Check | Result | Scope |
|---|---|---|
| Full backend suite | 563 passed; 5 dependency deprecation warnings; 13.81 s in final full run | 534 inherited regressions + 29 new runner/SDK/guard tests; paid network disabled |
| Frontend unit/component suite | 13 passed across 3 files | Includes fragmented safety SSE parsing and interrupted-stream behavior |
| Production frontend build | TypeScript and Vite passed | Existing stylesheet retained; final bundle built successfully |
| New engine browser suite | 8 passed | Desktop Chromium and Pixel 7 profiles; actual local primary backend with no key; session startup, history, case isolation, safety persistence/deduplication and workflow drawer |
| Legacy browser suite | 9 passed, 3 expected skips | Original chat, attachment, history, journey and system-information coverage; legacy runner, paid calls disabled |
| Ruff | All checks passed for `app`, `tests`, `scripts` | Full application/test/script lint, not just new modules |
| Python compile | Passed | All backend application modules |
| A–H offline protocol matrix | 8 recorded, all applicable mechanical checks true | Scripted research/answer fixtures; not a model-quality/legal evaluation |
| Installed OpenAI SDK transport mocks | Passed within backend suite | Actual SDK serializes strict Responses/tools schemas; mock HTTP handles parsing, usage hooks, refusal, incomplete and invalid output |
| Paid live evaluation guard | Refused before transmission under default configuration | No paid API request executed |

Backend machine-readable report: `evals/raw_outputs/v2-implementation-offline.xml`. A–H records: `evals/reports/primary-v2-offline.json`. Primary browser configuration: `frontend/playwright.primary.config.ts`; original comparison browser configuration: `frontend/playwright.config.ts`.

## Representative behavior established by tests

- One primary request can publish an exact attributed user extract without separate interpretation/intake/reviewer calls. This is mechanically constrained assistance, not proof that a one-call model summary is legally reliable.
- Legal claims and external assertions hidden under practical labels cannot be published without their required public evidence and semantic approval.
- A failed reviewer preserves independently supported quoted facts, and a failed re-review preserves earlier support only for unchanged prose. Changed unsupported material stays withheld.
- A partially rejected requested document does not become a misleading incomplete clean artifact.
- Reviewed patches commit once with source provenance, while unrelated educational requests cannot mutate case facts even if an erroneous reviewer approves the proposed patch.
- The primary session preserves original encrypted reasoning/tool items during tool continuation and receives the actual evidence/limitations response.
- Independent search queries and different source-host fetches overlap. A barrier-based test would fail if those operations ran sequentially.
- Query/call/token/spend reservations are shared atomically; stale cache entries expire; private-origin entries are rejected; foreign official origin does not imply Indian jurisdiction.
- Safety guidance is persisted before streaming, precedes final output, survives provider failure/reload and is deduplicated. Expired emergency references suppress contact numbers without suppressing generic protective help.
- Public PDFs larger than the extraction-page allowance yield explicitly limited passages; omitted pages are not implied to have been assessed.
- An inherited Strict Mode first-visitor race was identified during screenshot QA and fixed by guarding anonymous-session initialization. A desktop/mobile browser test asserts one bootstrap per mount and no startup alert.

## Visual verification

Desktop and mobile workflow screenshots were inspected after the startup fix. The prior `conversation_not_found` alert was absent. Saved QA images are in `docs/qa/v2-workflow-desktop.png` and `docs/qa/v2-workflow-mobile.png`.

The V1/V2 `frontend/src/styles.css` hashes both equal `cfa0c8f02a57afa1abe8283fec18774c91cde0c6bb8ac456cc0bcee4e0d05357`. UI changes are functional safety-stream, session-initialization, source-label and actual-workflow integrations. No new visual system or frontend framework was introduced.

## Before/after conclusions supported by evidence

The inherited configured flow has separate interpretation, batched generation and independent review requests, with optional search/extraction/repair. The new mechanically constrained quote/template fixture uses one primary request. Original free-prose legal synthesis is conservatively reviewed and may still require several provider requests. Concurrent research is established by software tests, not production measurements.

Saved V1 live reports record approximately 59–80 seconds on individual public prompts; the Amazon example recorded 79.557 s with three generation/search requests plus one embedding. Those historical runs are not the current-code baseline and are not comparable with scripted offline execution. No percentage latency, cost or legal-accuracy improvement is claimed.

No real primary/review/search model was called or compared during implementation. Offline A–H answers deliberately contain approved preparation/fallback text and no invented legal conclusions. Their timings measure local protocol execution only. Do not present these records as satisfying the substantive legal expectations of A–H.

## Remaining release gates

Configure V2's backend key and an explicit numeric live case/request/USD allowance with dated pricing. Use the guarded live harness for a minimal capability smoke test followed by bounded paired legacy/V2 scenarios. Have a qualified Indian legal reviewer assess primary-source applicability and real outputs, especially police/custody, current criminal procedure, state wages and formal filing eligibility. Resolve the PDF engine's AGPL/commercial distribution arrangement. Validate live voice/OCR dependencies and the intended deployment environment separately.

The source implementation and offline integration are ready; live quality/performance and legal certification are not established. See `docs/v2-implementation-status.md` for the precise plan reconciliation.
