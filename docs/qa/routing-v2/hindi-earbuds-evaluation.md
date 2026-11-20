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

## First focused retest and second fix

The first fix was deployed to preview commit `a054a8f`. The exact Hindi scenario now loaded eight source passages, chose Verified, performed no web searches, and produced useful factual preparation. However, router + applicability + answer left only about 18 seconds for independent review, which timed out. Publication correctly withheld the official-route claims. Actual result: **partial assistance, core routing acceptance still failed**, HTTP 200, 69.44 seconds including bootstrap/network; 58.032 seconds inside the runner. Four reserved provider calls, 28,878 reported tokens; billed cost remains unknown. See `hindi-earbuds-fixed-preview-live.actual.json`.

A second focused fix retains the same Sol/medium configuration and all publication checks: the router can return a complete applicability assessment with the route when evidence has not changed. Verified executes that assessment without a duplicate call; new research evidence still requires a fresh assessment. Router input omits irrelevant output templates. The answer is instructed to prioritize the user's immediate next step in 150–220 words rather than produce optional doctrine and redundant claims. Draft requests may be longer. This is LLM-generated guidance, not a scripted response.

Second-fix targeted verification: 70 tests passed, including assessment reuse and mandatory reassessment after research. The first-fix full backend regression passed: 777 tests, 4 skipped. Final live result will be recorded separately; these checks alone do not establish acceptance.

## Final live result — commit 196d027

Tested preview: https://nyay-sathi-q7smc8dmc-anandmehtaashutosh-6445s-projects.vercel.app/

Actual HTTP 200; **Verified** route; **three** provider calls (router/applicability combined, primary, independent reviewer), all `gpt-5.6-sol` with the medium reasoning configuration. Eight initial source passages, no web searches, no research batches. Runner elapsed **49.773 seconds**; complete probe elapsed **64.08 seconds** including health/bootstrap/create/network. Independent semantic review completed, published claims passed checks, and citations were included. Reported usage: 29,990 tokens; actual billed cost remains unknown. Actual response is saved in `hindi-earbuds-final-preview-live.actual.json`.

| Criterion | Actual result |
| --- | --- |
| Hindi reply | Pass: body and follow-up in Hindi, with some untranslated official terms. |
| Preserve ₹5,000, one-week failure and refused assistance | Pass: no invented company/order identifier or exact purchase date. |
| Non-court next step | Pass: written platform grievance, then NCH/1915/consumerhelpline.gov.in, with no promised refund. Court is a last option, not the immediate recommendation. |
| Official citations and review | Pass for the executed publication pipeline: four cited source entries and completed independent semantic review. This is not lawyer certification or a complete amendment audit. Current NCH operation independently checked against the Department's page. |
| Truthful actions | Pass: gave instructions; did not claim to send, file or resolve the complaint. |
| One essential follow-up at a time | Needs improvement: one question combined India applicability and prior contact with the formal grievance officer. |
| Simple, short language | Needs improvement: more verbose than requested and used “Grievance Officer” and “District Consumer Commission” without a plain Hindi explanation. |
| Usable complaint draft | Not fully tested: offered drafting and described required facts; this input did not request the finished draft. No additional live follow-up is claimed. |

Final offline regression: **778 passed, 4 skipped**, with five existing dependency deprecation warnings. No frontend/color/homepage changes. Production was not promoted.

## Remaining issues and next actions

- **5/10, verified latency degradation:** approximately 50 seconds inside the agent, 64 seconds for the cold multi-request probe. The useful reply now fits the hosted deadline, but more conversational speed is needed. Owner/implementer: defer broader performance work; measure warm UI turns and trim optional content before case-study recording. Do not remove review or lower the owner's chosen reasoning setting to get a faster result.
- **3/10, verified usability issue:** combined follow-up and untranslated terms increase effort for a first-time user. Owner/implementer: record for prompt refinement; ask only the next material fact and explain official terms in Hindi. No further paid rerun in this turn solely for polish.
- **3/10, inherited metadata naming issue:** `verification.legal_certification=true` means a previously indexed “certified proposition” was used; it does not establish professional legal certification. The UI certification claim was already removed. Owner/implementer: rename this internal field in a separately tested compatibility change; do not describe this result as legally certified.
- **6/10, unverified scope:** this live example does not establish a completed draft follow-up, every route's quality, current-law coverage, durable storage or a numerical total billing cap. Owner/implementer: keep those acceptance items open. Real billed totals require provider billing evidence; token usage is not a receipt.

The relevant supported slice now works for this example: a real Hindi response, official pre-litigation next steps, grounded source references and completed independent review. The broader MVP is not declared complete.
