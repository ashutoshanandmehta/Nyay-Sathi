# Nyay Saathi V2

India-focused legal-information and case-preparation assistant using the existing V1 React interface and a bounded primary reasoning agent. V1's original application remains in its own directory. No user database, uploads or API key were migrated.

The default backend is `primary_agent`. It understands the question, requests selective research, receives fetched evidence and prepares an answer in one logical session. Original prose and consequential advice receive independent semantic review; exact attributed extracts and approved low-risk templates can skip that call. Runtime checks citation identity, dependencies and private-state authorization. This is evidence assessment, not legal certification or advocate representation.

## Start locally

Requirements: Python 3.11+, `uv`, Node compatible with the locked Vite dependencies. Verified locally with Python 3.12.16. Tesseract English/Hindi is optional for OCR; absence is reported explicitly.

```sh
cp .env.example .env
# Add your OpenAI key to .env, never to frontend code.
cd backend
uv sync --frozen
uv run uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [the local app](http://localhost:5173). Without a key, the app supports chat persistence, documents, exports and approved emergency guidance; researched AI answers remain unavailable. Model defaults are inherited configuration, not a claim of current account access. No paid API calls were made during this implementation.

## Preserved features

- V1 branding, layout, stylesheet, desktop/mobile navigation and chat interface.
- Browser ownership, CSRF, history, rename/delete, request replay protection and durable commit receipts.
- English/Hindi/Hinglish, attachments, extraction preview/correction, draft versioning, case workspace and exports.
- Existing voice transcription/speech endpoints and practice/drafting interactions. Live voice is not newly validated.
- Source drawer with exact fetched passages and stable source identities.

New functionality includes concurrent bounded research, public evidence cache, an early persisted safety stream, one targeted repair with required re-review, an updated workflow drawer, and per-turn accounting. Public text is untrusted data; prompts do not grant tools authority to send, file or sign anything.

## Budget and configuration

See [.env.example](.env.example) and [runtime architecture](docs/v2-architecture.md). Routine defaults are 6 provider requests, 3 primary rounds including repair, 2 research batches, 3 queries, 6 attempted downloads, 5 selected passages per batch, a 60-second runner deadline and a 20-second research-batch deadline. Shared reservations can prevent later optional work. V2 never embeds the corpus on startup. Optional vectors require explicit index maintenance.

Live development evaluations default to zero cases, zero calls and zero dollars. Use `python -m scripts.evaluate_primary` for free offline protocol fixtures. A live evaluation additionally requires explicit caps, a key, dated per-model pricing and `--live`. Search-generation calls count as provider requests. Monetary estimates are distinct from actual billing; unknown usage is never reported as free.

`ASSISTANT_ENGINE=legacy` selects the inherited graph for comparisons. Both engines preserve the API shape; actual V1 data migration and deployment are separate operations.

## Verify

```sh
cd backend
uv run pytest -q
uv run python -m scripts.evaluate_primary
uv run ruff check app/agent
cd ../frontend
npm test
npm run build
npm run test:e2e
npm run test:e2e -- --config playwright.primary.config.ts
```

The first browser suite runs the legacy engine to preserve its established regression coverage; the second runs the new default engine. Both disable real AI calls. Do not run both browser suites concurrently: their isolated servers use the same test ports. Install Playwright Chromium if unavailable: `npx playwright install chromium`.

## Evidence and limits

Read [implementation status](docs/v2-implementation-status.md), [evaluation report](evals/reports/v2-implementation.md), [reuse and licenses](docs/v2-reuse-and-licenses.md), and the [verified plan](V2_EXECUTION_PLAN.md).

Offline fixtures and SDK transport mocks establish software behavior, not model reasoning quality, live API compatibility or legal correctness. Real model/search benchmarks, a measured before/after latency/cost improvement, qualified legal review, live voice and production deployment remain unverified. Historical live reports in this repository are V1 records and are labelled accordingly. The retained PDF engine requires an AGPL/commercial distribution decision before release; no license purchase or proprietary-release compliance is claimed.

The existing consumer corpus contains 621 candidate passages and has known amendment/treatment gaps. Dynamic research can address other topics, but complete law coverage and current judicial treatment are not guaranteed. Source acquisition, applicability and legal currency are separate. Expired emergency contacts are suppressed pending revalidation.

For the original setup and architecture, see [the preserved V1 README](docs/v1-readme-reference.md).
