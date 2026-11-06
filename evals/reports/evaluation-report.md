# Evaluation report

Latest independent interpretation/task-routing checks: [6 November routing report](request-routing-2026-11-06.md). New live evaluation remains intentionally paused.

Latest complaint-resolution results: [6 November increment](resolution-2026-11-06.md). The earlier baseline below is retained as historical validation, not the latest totals.

Run date: 2026-11-05

## Objective checks executed

- Backend deterministic suite: 107 passed. It covered 45 scenario contracts plus multi-request detection, natural scoped confirmation, ₹18,000→₹2,300 correction, completed-action handling, materially conflicting draft dates without overwriting the prior confirmed fact, IST context, private evidence search, safe arithmetic/date separation, feedback-loop revision, internal-output separation, restart, owner/case isolation, CSRF, idempotency, failed-turn retry recovery, concurrent-turn integrity, checkpoint deletion, retrieval rewriting, prompt injection, OCR failure, visible-citation resolution, expanded-corpus contracts, grounding gates, playbook/vector separation, private upload registration, structured workspace provenance, evidence semantics, lawyer-pack export structure, and live system-metadata contracts.
- Frontend component suite: 7 passed. It covered permanent New chat access, failed-send text preservation, Markdown raw-HTML rejection, source inspection, case/evidence/contradiction presentation, knowledge-base counts, and workflow branches.
- Frontend production build: passed with Vite 8.3.5 and TypeScript 7.0.2.
- Browser workflow: 3 passed and 3 project-specific skips. Desktop covered first visit, offline turn, refresh resume, immediate independent New chat, layered Knowledge Base tabs, official sources, lawyer preparation, and Agent Workflow drawers. Mobile covered composer, sidebar drawer, and case drawer. The browser run uses dedicated ports and an explicitly offline backend so it cannot consume a developer's live model budget.
- Backend Ruff check: passed.
- Reproducible official-source ingestion: 18 official documents succeeded, two discovery/register pages were deliberately skipped, and zero enabled sources failed. It produced 607 full-source passages; with 14 curated excerpts, BM25 and Chroma each contain 621 passages under corpus `956293ec74ee`.
- Synthetic Hindi DOCX and PDF exports were rendered and visually inspected; both fit on one page without clipped text, the PDF was A4 with an embedded Devanagari font, and the DOCX ZIP structure passed validation.
- Docker Compose execution was not run because the Docker command is unavailable on this host; native backend, frontend, and browser runs were executed instead.

## Live model smoke evaluation

Run after the user configured `OPENAI_API_KEY`. Earlier smoke runs covered a generic scope question, grounded defective-product/refund retrieval, playbook branching, and expanded structured workspace updates; their synthetic chats and checkpoints were deleted.

The new non-delivery regression was run three times through the real local HTTP API within the configured three-case budget. Run 1 produced both requested outputs but duplicated its follow-up question; the renderer was fixed. Run 2 removed the duplicate and passed the then-current checks, but manual inspection found that its single question asked for dates instead of the desired resolution; the response and review prompts were fixed. Run 3 used 10,054 reported tokens, passed feedback review without revision, produced the evidence checklist and provisional factual summary, did not infer the missing year, did not treat an absent OTP/photo as proof, rendered no internal keys, and asked one desired-resolution question. Manual inspection then found it began directly with a heading rather than the requested brief acknowledgement. The response and reviewer prompts plus the future live-run assertion were tightened; that final acknowledgement-only adjustment was not re-run live because the configured three-case live budget had been reached. It is covered by deterministic prompt and feedback-loop tests, not claimed as live-verified.

These are integration observations, not evidence of legal correctness. Transcription, Realtime speech, and operator web discovery were not live-tested.

## Human review

Not performed. Lawyer review remains pending. Automated checks and model agreement cannot establish legal correctness.

## Raw output

`evals/raw_outputs/deterministic-2026-11-05.jsonl` contains observable extractions, retrieved passage IDs, memory updates, prompt/corpus versions, timestamps, latency, and empty token usage for all 45 scenarios. `evals/raw_outputs/live-2026-11-05.jsonl` records earlier live smoke turns. `evals/raw_outputs/live-conversation-2026-11-05.jsonl` records all three new regression attempts, including the failed first run, observable outputs, feedback events, verification, latency, token use and objective checks. These files contain no private chain-of-thought.
