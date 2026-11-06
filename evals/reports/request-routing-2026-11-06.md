# Independent request routing: executed validation

Date: 6 November 2026. All new evaluations are offline. No real-model or staging-with-live-provider evaluation was authorized or run.

## Results

- Backend pytest: **457 passed**, no failures. JUnit: `evals/raw_outputs/pytest-request-routing-2026-11-06.xml`. Seven existing PyMuPDF/Chroma deprecation warnings remain.
- Ruff: passed across `app`, `tests`, `scripts`.
- Frontend: **10 component tests passed**; TypeScript/Vite production build passed.
- Playwright: **9 passed, 3 intentional desktop/mobile project-specific skips**. The new unrelated-question journey checks actual persisted case memory before/after a topic change and refresh on desktop and mobile. The test server explicitly has an empty OpenAI key.
- Offline HTTP regression runner: **16/16 contracts passed**, **16/16 workflow matches**, **0 unintended case mutations** on those fixtures. Median measured HTTP turn latency: **29 ms**, excluding AI because no model runs. Token consumption and live model calls in this runner: **0**. These are synthetic offline results, not real-world routing accuracy or response latency.

Raw observable HTTP records: `evals/raw_outputs/request-routing-offline-2026-11-06.jsonl`. Metrics: `evals/reports/request-routing-metrics.json`. Inputs, actual outputs, task contracts, tool outcomes, memory changes, versions, timestamps and latency are retained; no private chain-of-thought or credentials are recorded.

## Covered contracts

Relationship-based hotel employment versus consumer booking; general IPO and animal-health requests; Hindi/Hinglish; brand/industry words without a dispute; unfamiliar organizations; mixed safety/general/legal tasks; urgent task priority; interpreter-before-intake ordering; exact legal task excerpts; failed interpretation remaining read-only; schema rejection of owner/case arguments and duplicate IDs; unrelated-question and ambiguous-confirmation continuity; distinct disputes not overwriting existing cases; user-edited draft preservation; transaction rollback before stale marking/audit writes; privacy-filtered public queries; private-network/unsafe URL rejection; actual search success/failure/no-results records; truthful no-results search reporting; rejection of invented browsing limitations; task coverage; unverified authority claims; preparation versus filing eligibility; date arithmetic versus statutory clocks; mandatory draft fields; and the existing citation/owner/isolation/deletion regressions.

Provider/model doubles are explicitly labelled in tests. They verify adapter integration and deterministic checks, not the model's ability to interpret natural language. The interpreter's structured-output call is tested with an injected model double; actual provider compatibility and semantic quality remain live-validation tasks.

## Failures found and fixed

- Existing refund intake variants initially failed the conservative fallback and were corrected without reinstating hotel/brand domain assumptions.
- The search adapter fixture omitted the provider's completion status; it now models the real success contract. Missing or incomplete provider execution is rejected.
- The full browser suite exhausted the shared localhost request limit. The limit became configurable; only the isolated suite uses 600/minute, while the default remains 120. A new assertion was scoped to the conversation because sidebar previews duplicate answer text.
- A completed search with no usable sources must still support “I searched, but found no supporting results.” Execution completion and evidence sufficiency are now separate.

## Release limits and next acceptance gates

The implementation is integrated and offline-tested. It does not establish measured real-model accuracy, veterinary/medical correctness, success on current IPO questions, passing live web citations or legal admissibility. The earlier failed live web run remains a failed result and has not been overwritten or relabelled.

Before claiming those capabilities verified: explicitly authorize a small model/token/search budget; run a controlled synthetic mixed-request and unfamiliar-organization set; record actual task classification, model IDs, tool events, fetched passages, tokens and end-to-end latency; investigate every unsupported authority/citation/tool-use claim; then test the full staging journey. Qualified Indian-lawyer review remains pending. Automated agreement does not establish legal correctness.

Consumer policies assess preparation rather than complete filing admissibility. Other legal domains remain bounded research/handoff. Case-specific statutory deadline calculators, automatic filing, authenticated platform procedures and clinical expertise are not supplied by this increment.
