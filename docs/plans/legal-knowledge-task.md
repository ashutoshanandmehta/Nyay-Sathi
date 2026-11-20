# Legal knowledge and retrieval task

Owner: Antigravity. Assigned by the product owner on 20 November 2026. Status: ready for handoff; this coordinating chat has not dispatched execution.

## Objective and scope

Build the initial source-traceable legal knowledge pack and retrieval component for Nyay Saathi's consumer complaints, financial fraud and banking/payment prototype. Begin with a small sufficient pack supporting explicit demonstration scenarios. Reuse existing source material only after checking provenance and current applicability. Existing labels such as `certified` are not independent evidence of legal review.

Read [the shared checklist](../../checklist.md), [the original product blueprint](product-blueprint-reference.md), [the implementation review](agy-implementation-review-2026-11-20.md), and [the agent architecture](supabase-resumable-agent-architecture-2026-11-20.md).

## First deliverable: shared boundary

Before bulk ingestion, define and commit a typed retrieval interface and representative fixtures that the backend chat can use independently. The request includes query, confirmed case region, incident/as-of date where known, and a bounded result limit. Results include stable passage/document IDs, exact text/locator, canonical official source URL, source authority, applicable region, known validity interval, acquisition/version metadata, review state and limitations.

Handle missing dates and regions explicitly; do not invent them. Retrieve applicable national law alongside regional material. Include definitions, exceptions and cross-references required to interpret selected passages. Preserve continuity of IDs across updates.

## Implementation deliverables

- A documented initial coverage declaration and real, versioned source pack from official legislation/regulator/court sources as appropriate to the selected scenarios.
- Reproducible import/indexing code compatible with the agreed Supabase/PostgreSQL architecture; explain which lexical/vector functionality is actually implemented and tested.
- Retrieval implementation behind the shared interface, including applicability filters, deduplication, provenance and explicit no-support outcomes.
- Representative expected-evidence tests for refund/defective-product and payment/fraud questions, including unknown date/region, national-plus-state material, amended/retired material and unsupported questions.
- A source refresh/review plan, acquisition log and unresolved legal-quality limitations. Automated retrieval checks do not substitute for qualified content review.

## Ownership and integration

Own legal source data, its ingestion/retrieval modules and related tests. Coordinate any changes to shared contracts and migration numbering with the backend owner before editing them. Do not independently rewrite agent orchestration, Google adapters, authentication or frontend transport.

Preserve the shared Vercel demo and both existing worktrees. The newer implementation currently lives in `/Users/ashutoshanand/.gemini/antigravity/worktrees/Nyay Sathi V2/android_supabase_migration_plan`; the primary project is `/Users/ashutoshanand/Downloads/Nyay Sathi V2`. Both have uncommitted work. Inventory it, establish an isolated working baseline, and avoid resetting or overwriting either copy. A fresh worktree from HEAD alone will not contain all existing uncommitted implementation files.

Do not deploy migrations or make unbudgeted paid embedding/model calls as part of offline acceptance. Prepare concrete deployment artifacts and report required configuration separately.

## Acceptance and report

The backend chat can consume the fixture and actual retrieval implementation through the same interface. Expected passages retain correct IDs, locators, source/version metadata and applicability. Unsupported coverage produces a limitation rather than invented evidence. Update only this workstream's checklist items with changed files, test commands/results, remaining limitations and integration requirements. Do not mark hosted or legal-quality verification complete from synthetic tests.
