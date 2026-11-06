# V2 implementation status — 7 November 2026

## Implemented

- V1 application source seeded into isolated V2 directory; original styles, components, endpoints and supported feature surfaces reused. Fresh dependencies installed from existing locks; independent runtime state; no copied API key or user database.
- Default primary Responses runner with typed answers and read-only research/safety tools, original context, stateless continuation, configurable models, strict schemas, refusal/truncation handling and bounded rounds.
- Dynamic public legal research without a closed legal-topic/organization whitelist; concurrent queries and host-grouped safe source fetch; URL/content deduplication; relevance/Indian-authority ranking; exact passage snapshots and honest unknown metadata.
- Additive persistent public-evidence cache with TTL/version records and explicit invalidation; saved official candidates remain candidates rather than legal truth. No automatic paid embeddings on import/startup.
- Mechanical claim/provenance/dependency checks, conservative adaptive semantic review, one targeted repair, required re-review and preservation of independently useful content. Incomplete document artifacts are not saved as clean correspondence.
- Existing staged case patches, case authorization, provenance, version protection, idempotency, recovery receipts and artifact persistence integrated with the new engine.
- Immediate persisted safety SSE guidance through the existing UI, model-requestable safety, stale-contact suppression, refresh/retry deduplication and updated workflow view.
- Atomic request/token/spend forecast guards, explicit output/download/time limits, nullable cost estimates, search-call accounting, first-guidance/stage timing and privacy-limited telemetry.
- PDF adapter preserving existing engine behavior; explicitly partial public-PDF extraction for large laws; retained private document/OCR limits and export features.
- Offline A–H protocol fixtures and separately guarded live evaluation harness; new runner, transport, concurrency, cache, safety and persistence tests; reused frontend tests/build and legacy/new desktop/mobile browser suites.
- Updated README, architecture, cache commands, reuse/license record and reference source manifest.

## Validation boundaries and work requiring external inputs

1. No paid live primary/review/search call was executed. Installed-SDK HTTP mocks exercise actual request serialization, parsing, usage hooks, refusals and incomplete output, but do not establish provider-account/model access or real answer quality. Configure a numeric case/call/USD evaluation budget and key to run the live harness.
2. No before/after live latency or cost improvement is claimed. Historical V1 outputs are preserved as reference; offline timings cannot be compared to their network/model timings. A paired repeated benchmark remains necessary to assert a performance gain.
3. A–H fixtures verify protocol, isolation and failure behavior. They do not certify legal outcomes. Qualified Indian legal review of scenario evidence and real outputs remains outstanding.
4. Current-law coverage relies on existing corpus candidates plus dynamic retrieval. A complete curated BNSS/employment/judgment evidence pack, automated amendment tracking and subsequent-treatment service are not implemented. The source directory provides official starting points; unavailable or incomplete sources remain explicit limitations.
5. Semantic review is deliberately conservative: all original prose currently uses a reviewer. Exact extracts and approved templates can use one primary call. Broadly skipping review for legal synthesis has not been validated and is not enabled.
6. Live transcription, speech, full OCR engine/language availability and production deployment were not newly exercised. Existing endpoints and regression coverage are retained. No deployment was performed.
7. PyMuPDF distribution/licensing requires an owner decision before release. The adapter is in place; no alternate PDF engine or commercial license was selected.
8. Single-host SQLite and existing anonymous-cookie ownership remain. Cross-device recovery, multi-instance coordination and production operational assurance are outside the implemented local architecture.

## Plan reconciliation

Phases 0–6 have implementation and offline integration coverage, subject to the explicit source-pack/licensing/live-feature limitations above. Phase 7 has a working offline harness and budget-enforced live entry point; paid comparative and legal evaluation remains pending. Phase 8 documentation and selectable runner are present; default V2 is an unvalidated-live preview, and redundant legacy code remains deliberately available until live comparison supports retirement. The old graph has been removed from the default primary execution path, not deleted from the repository.

See [evaluation results](../evals/reports/v2-implementation.md) for executed checks and [V2 plan](../V2_EXECUTION_PLAN.md) for original acceptance gates.
