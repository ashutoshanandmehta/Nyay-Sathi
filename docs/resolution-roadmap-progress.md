# Resolution roadmap execution — 6 November 2026

Status: core implementation integrated; broader roadmap and legal validation remain open.

## Implemented

- Append-only complaint events with message/document provenance and corrections that supersede earlier reports. SQLite persists events and recommendations alongside case memory; ownership remains case-scoped.
- Submissions, replies, commitments, reported receipt of remedies, ticket closure, satisfaction and severity are separate concepts. A processed refund or closed ticket is not a verified credit.
- A data-driven recipient registry covers Amazon, Flipkart, Blinkit, Instamart, Agoda and OYO. Verification limitations are recorded; authenticated Agoda/OYO flows and unknown grievance contacts are not presented as verified.
- Conditional preparation routes replace a mandatory escalation ladder. Prior submissions are reused, explicit destination requests are respected, settlement/stop requests prevent automatic escalation, and UPI alone does not select RBI.
- Tri-state eligibility results preserve missing jurisdiction, consumer-purpose, prior-proceeding and timing inputs. These are preparation checks, not a comprehensive legal admissibility decision.
- Versioned consideration-based fee slabs and pecuniary bands, qualitative preparation effort, other possible expenses and unknown outcome/waiting estimates. No invented success probabilities or forum-derived averages.
- Chat, email, form and formal drafting strategies; a separate clean document field; editable draft preview and owner-scoped DOCX/PDF export. Nothing is sent, filed, signed or sworn.
- Complaint journey and conditional route comparisons inside the existing case drawer; default entry remains chat.
- An explicit LangGraph planning node connects intake/retrieval to generation and independent feedback review. Current selected language also reaches generation and revision.

## Design boundaries

`app/resolution` contains domain models and separate journey, recipient, eligibility, fee, trade-off and drafting services. The planner depends on policy contracts; channel strategies prepare material and have no submission capability. Platform procedures and rules are versioned data rather than one class per platform/issue combination. SQLite/Chroma and anonymous browser ownership remain in place; no database migration to PostgreSQL or new services were introduced.

## Validation and remaining work

See [evaluation report](../evals/reports/resolution-2026-11-06.md) for executed checks and failed live runs. The 240-case matrix is a synthetic combination of platform/stage/request contracts, not 240 independent legal evaluations.

- [x] Complaint history, outcome distinctions, conditional preparation, adaptive drafts and case-drawer integration.
- [x] Offline regression suite, frontend build/component checks and desktop/mobile workflow checks.
- [x] One actual live Blinkit drafting journey passed automated review; no claim of lawyer approval.
- [ ] Robust live web citation formatting: a recorded web-assisted run was withheld; subsequent changes are offline-tested only.
- [ ] Complete, independently validated sector eligibility/deadline calculators for RBI, travel and food-safety matters.
- [ ] Authenticated filing-form walkthroughs and platform-specific current recipient verification where marked unknown.
- [ ] Representative community-experience collection, freshness jobs, bias assessment and measured friction/outcome data.
- [ ] Reminders, supervised submission adapters and operational metrics; no submission integration is claimed.
- [ ] New correspondence export visual/Hindi validation and qualified Indian-lawyer review.

At the user's request, further development validation will use offline tests and labelled fixtures. No additional live OpenAI evaluation is authorized without an explicit request.
