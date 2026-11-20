# Hindi ₹5,000 earbuds live evaluation — 20 November 2026

The owner explicitly requested this exact scenario as a live app test with a Hindi reply. Each recorded run is a separate isolated anonymous test conversation, with `language=hi`. No actual grievance was submitted to a company, helpline or authority. API keys were neither read nor copied. Paid provider use occurred inside the app; complete billed cost is unavailable.

## Initial actual results

1. Existing production (`primary-agent-v2.0`): HTTP 200 in 17.39 seconds. Body was mostly English despite the Hindi setting and recommended CORE rather than the verified current NCH route. **Failed** language and complaint-routing expectations. See `hindi-earbuds-live.actual.json`. This result is not evidence for the new architecture.
2. Initial new-routing preview (`primary-agent-v2.1-routed`): HTTP 200 in 60.53 seconds, selected Research, loaded zero initial source passages, ran two research batches, and exhausted the 58-second runner deadline. Body was Hindi but contained only evidence-preservation and verification-unavailable templates. No actionable NCH step or draft. **Failed** the core complaint journey. See `hindi-earbuds-preview-live.actual.json`. The publication flag describes safe template claims only; it does not mean the requested journey succeeded.

Initial remaining impact: **8/10, verified core-flow defect**. Keep new routing out of production until the scenario produces useful assistance.

## Focused fixes

- Added consumer Hindi/Hinglish/English concept expansion to existing retrieval (not response generation or deterministic routing).
- Initial context now includes relevant official corpus candidates as well as certified propositions and statutory packs. Corpus passages remain candidates; applicability assessment and independent claim review still apply.
- Rechecked NCH through the Department of Consumer Affairs page, including 1915 and the pre-litigation channel. Updated both existing data copies without inventing a statutory effective date, refund entitlement or resolution guarantee.
- A new research tool round requires enough remaining time for research and publication checks. Context indicates prior research; the hosted deadline and review safeguards were not increased or bypassed.
- Offline reproduction now retrieves the current NCH passage for the Hindi earbuds query. Regression checks cover corpus provenance and refusal to repeat research when only 28 seconds remain. Targeted checks: 69 passed.

Official verification: https://consumeraffairs.gov.in/pages/nch and https://consumerhelpline.gov.in/public/about . The latter describes pre-litigation assistance, not a guaranteed refund. Direct portal fetch was unavailable; the Department's page was successfully verified through official search results.

Retest pending at the time of this commit. Do not infer success from offline checks or deployment readiness.
