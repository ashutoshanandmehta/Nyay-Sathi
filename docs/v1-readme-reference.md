# Nyay Saathi

Nyay Saathi is a runnable conversational AI legal-information and case-preparation assistant for ordinary people in India. Its deep MVP covers consumer refunds, defective goods, non-delivery, and refusal of a stated return or refund commitment. Other matters receive factual organisation and a handoff brief without unsupported legal conclusions.

It is not a licensed advocate, does not represent users, does not guarantee outcomes, and does not create lawyer-client privilege. Nothing is automatically sent, filed, signed, or submitted.

## What works

- Independent versioned request interpretation before legal intake, per-task routing for mixed/general/safety/legal requests, runtime tool outcomes, and validated case-update proposals. See [routing and safeguards](docs/request-routing.md). New semantic/live research behaviour remains pending live validation; API-credit conservation is in force.

- Immediate anonymous chat with multiple persistent cases, browser-owner isolation, rename/delete, resume after restart, and a permanent New chat action.
- Typed LangGraph orchestration with SQLite checkpoints, multi-layer memory, bounded IST-aware context, scoped natural confirmation, correction provenance, contradictions, idempotent requests, and per-case turn locks.
- Layered shared knowledge: official-source register, versioned intake/evidence playbooks, explicit procedure gates, drafting structures, a deliberately small judgment set, lawyer-preparation guidance, and bounded official referrals.
- Contextual query rewriting over 621 official-source passages, BM25 plus OpenAI/Chroma retrieval, reciprocal-rank fusion, inspectable passages, exact visible-citation resolution, and verification gates. Playbooks and private case records are deliberately kept outside the legal vector index.
- Bounded official web research when the local corpus leaves a public information gap: typed privacy-safe query planning, safe page/PDF fetching, case-scoped source snapshots, live progress and independent answer review. See [configuration, tests and live limitations](docs/web-research.md).
- Task-scoped answer units receive independent claim/task review, at most one repair, and deterministic evidence/eligibility checks. Verified drafts can survive a failed independent lookup. Canonical citation IDs, staged case updates and bounded budgets are described in [publication architecture](docs/answer-unit-publication.md). Live progress stages are streamed while processing.
- PDF, PNG/JPEG, and text evidence; extraction preview/correction; OCR fallback with explicit partial/unreadable states.
- Drafting, revision, and practice through the conversation when OpenAI is configured; stale drafts after material fact changes.
- English, Hindi, and Hinglish preferences, recorded-file transcription, and AI-disclosed speech for verified answers.
- Editable DOCX correspondence/case pack, PDF lawyer briefing pack, and JSON export with overview, evidence-linked chronology, gaps, correspondence, review issues, urgent matters, and consultation questions.
- Responsive React interface with a desktop sidebar, mobile drawer, sticky composer, attachments, microphone, Markdown, sources, drafts, and case drawer.

## Native development

Requirements: Python 3.11+, Node 20+, and optionally Tesseract with English/Hindi data for OCR. This repository was verified with Python 3.12.16 and Node 26.3.0.

```bash
cp .env.example .env
# Add OPENAI_API_KEY only to .env on the backend side.

cd backend
../.tools/bin/uv sync --frozen --python 3.12
../.tools/bin/uv run uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. If `uv` is not already in `.tools/bin`, install it from https://docs.astral.sh/uv/ or use an existing `uv` executable; the committed `backend/uv.lock` remains authoritative.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:5173`. The Docker image includes Tesseract English/Hindi, Poppler, and Noto fonts. For HTTPS deployment set `COOKIE_SECURE=true`, set the exact frontend `APP_ORIGIN`, terminate TLS, and review retention and reverse-proxy limits.

## Model defaults

- `gpt-6-luna`: economical focused conversation and extraction.
- `gpt-6.1-sol`: higher-quality review model when model review is used.
- `text-embedding-3-small`: economical official-source embeddings.
- `gpt-transcribe`: current recorded-file transcription starting point.
- `gpt-realtime-2.1-mini`: current recommended lower-cost Realtime path for speech output; it replaces the deprecated Speech API model defaults.
- `gpt-6-astra`: operator-only official web-source discovery with government-domain filters; discovered pages are never legal support until separately fetched and ingested.

All names are configurable. The app does not silently substitute models or providers. Missing credentials leave persistence, uploads, source browsing, case organisation, and exports usable while displaying a configuration-required state.

## Source ingestion

```bash
cd backend
../.tools/bin/uv run python -m app.rag.ingest --json
../.tools/bin/uv run python -m scripts.rebuild_legal_index
```

The ingestion command permits only approved HTTPS government hosts, rechecks redirect targets and resolved network addresses, limits bytes and redirects, uses bounded retries/timeouts, preserves originals under the ignored `data/sources/originals/`, updates hashes, and writes stable page-located passages. The rebuild command synchronises persistent Chroma, removes stale vector IDs, and reports exact lexical/vector counts without printing the key. The current run downloaded 18 official documents, produced 607 full-source passages, combined them with 14 curated excerpts, and verified 621 vectors under corpus `956293ec74ee`. Failures are reported per source. The structured playbooks in `data/knowledge/` are versioned application guidance, not vector chunks or legal authority, and remain pending Indian-lawyer review.

Operator-only web discovery uses fixed non-personal topics and official-domain filters:

```bash
cd backend
../.tools/bin/uv run python -m app.rag.discover --topic consumer_procedure
```

Discovery returns candidate official URLs only. It never receives a case message or attachment, and its output cannot support a user-facing claim until the source register and allowlisted ingestion pipeline have fetched and parsed it.

## Checks

```bash
cd backend
../.tools/bin/uv run ruff check app tests
../.tools/bin/uv run pytest -q

cd ../frontend
npm test
npm run build
npm run test:e2e
```

Run the observable deterministic evaluation:

```bash
cd backend
../.tools/bin/uv run python -m scripts.run_deterministic_eval
../.tools/bin/uv run python -m scripts.run_answer_unit_regression
```

Live evaluation is intentionally separate and budgeted through `LIVE_EVAL_MAX_CASES` and `LIVE_EVAL_MAX_MODEL_CALLS`. The budgeted run covered structured intake, multi-request response generation, feedback review/revision, 621-passage embedding retrieval, and verification after a key was configured; transcription and Realtime speech remain unverified live.

## Privacy and deletion

Chats are available in this browser. Clearing browser cookies may remove your access. Export anything you want to keep. The server stores only a SHA-256 representation of the random owner token; the raw token stays in an HttpOnly cookie. A separate readable cookie supports double-submit CSRF validation. Local deletion removes case database rows, evidence files, generated exports, and the LangGraph thread. It cannot make claims about external API retention, backups, or copies the user exported.

See [architecture](docs/architecture.md), [memory and context](docs/memory-and-context.md), [research log](docs/research-log.md), [evaluation](evals/reports/evaluation-report.md), [limitations](docs/limitations.md), and the [legal review checklist](docs/legal-review-checklist.md).
