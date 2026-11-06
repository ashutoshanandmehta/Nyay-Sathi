# Web research validation — 2026-11-06

## Objective checks

- Backend: 139 deterministic tests passed, including 27 public-research tests. JUnit: `../raw_outputs/pytest-web-research-2026-11-06.xml`.
- Frontend: 8 component tests passed.
- TypeScript and Vite production build passed.
- Playwright: 5 desktop/mobile browser tests passed; 3 tests were intentionally skipped in inapplicable device projects.
- Ruff checks passed for application code and the new tests/evaluation scripts.
- Running application health and frontend HTTP checks passed; workflow endpoint reports graph-v4-public-research and eight logical calls per turn.

Deterministic research tests use explicitly labelled mock planner/provider/fetcher implementations. The compiled graph test confirms that web research runs before generation and review. These are not live-model results.

## Live observations

The first complete graph evaluation used an intentionally empty local corpus and actual OpenAI calls. It detected the missing public information, selected relevant NCH query intents, and returned a truthful limited answer after search tool-limit failures. It took 93.726 seconds and used eight logical model requests. No web passages supported that answer.

Two targeted search diagnostics followed: the first confirmed a provider adapter ValueError; the second, after explicitly requesting one search with low reasoning effort, returned one web-search event and official URLs. A separate real HTTP check also fetched the NCH About page with TLS hostname verification and IP pinning.

The final two-call generation/review slice fetched the three returned official URLs, selected three relevant excerpts, and generated a candidate. Independent review and the hard citation gate rejected its URL-as-locator citations. The user-facing output withheld the candidate. That slice took 21.774 seconds. Source hashes, excerpts, actual output, usage and findings are saved in `../raw_outputs/live-web-research-2026-11-06.jsonl`.

The final code adds a tightly scoped citation-format normaliser before review and unique HTML locators; deterministic tests verify both accepted exact identities and rejected unknown/ambiguous identities. The twelve-request live allowance was exhausted, so no full passing live rerun after those fixes is claimed. Additional model evaluation requires another explicit evaluation budget. Independent legal review remains pending.

## Remaining limits

Live latency is variable and can increase when web research is needed. Public-source coverage is constrained to approved national consumer topics and hosts. There is no automatic promotion into shared Chroma. Search results, official hosting, term overlap, and agreement by models are not legal correctness guarantees. Public PDF OCR is not implemented here. See `../../docs/web-research.md` for configuration, persistence, security boundaries and operational limitations.
