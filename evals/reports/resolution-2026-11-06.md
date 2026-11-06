# Complaint-resolution increment: executed validation

Date: 6 November 2026. This report distinguishes offline checks, live model observations and pending human review.

## Offline checks

- Backend pytest: **400 passed**, zero failures; JUnit: `evals/raw_outputs/pytest-resolution-2026-11-06.xml`. Seven dependency deprecation warnings remain (PyMuPDF/Chroma).
- Ruff: passed for `app`, `tests`, `scripts`.
- Frontend Vitest: **10 passed**. Production TypeScript/Vite build: passed.
- Full Playwright suite: **7 passed, 3 intentional project-specific skips**. Desktop/mobile coverage includes complaint history after refresh, distinct ticket-closure/satisfaction states, conditional next preparation, attachments, immediate composer clearing and independent chats. Tests run with an explicitly empty backend OpenAI key.
- The first new frontend run exposed missing test cleanup, which was fixed. The first expanded browser run exposed an actual offline event-ordering bug: an earlier refund promise overrode a later ticket closure because extraction used pattern order. Events now retain narrative order; a regression test covers this. Offline event descriptions use the relevant sentence rather than repeating the complete message for every event.
- The synthetic matrix has 240 platform/stage/request combinations; these are contract checks, not independent lawyer-reviewed cases or live results.
- Clean DOCX/PDF export structure and ownership are tested; visual and Hindi rendering of this new correspondence layout were not reverified in this increment.

## Actual live runs before the user's credit restriction

Twelve logical model calls were used across the following runs. Token usage and latency are recorded where returned. These are not a claim about monetary cost, legal correctness or guaranteed outcomes.

1. Full web-assisted graph with deliberately empty local retrieval: 7 calls, approximately 95.9 seconds. Actual search/fetch worked; independent review rejected insufficient support for a route description in the internal plan, and the answer was withheld. Existing approved primary-source policy passages were then attached to planning/review context.
2. Blinkit grievance/email journey with synthetic prior history: 3 calls, approximately 21.6 seconds. Passed automated factual/legal/tone review. Produced a clean short grievance email referencing the supplied ticket, preserved missing details as placeholders and offered a lower-effort alternative. It did not send or file anything.
3. Recheck using previously fetched actual public passages: 2 calls, approximately 29.2 seconds. Failed citation-locator matching and route alignment; unsupported output was withheld. This was not another complete search journey. Explicit NCH requests now take precedence over optional company-support preparation, subject to safety/contradiction gates; that change is offline-tested only. The web citation path still needs further investigation and live verification when explicitly authorized.

Raw records:

- `evals/raw_outputs/live-web-research-2026-11-06.jsonl`
- `evals/raw_outputs/live-resolution-2026-11-06.jsonl`
- `evals/raw_outputs/live-web-review-recheck-2026-11-06.jsonl`

Further live OpenAI testing is stopped at the user's request. Failed results are retained, not rewritten as passes.

## Pending

Qualified Indian-lawyer review, authenticated platform/filing flow verification, comprehensive sector deadline/eligibility calculators, representative friction/outcome data, new export visual QA and production operational evaluation remain pending. Automated model agreement does not establish legal correctness.
