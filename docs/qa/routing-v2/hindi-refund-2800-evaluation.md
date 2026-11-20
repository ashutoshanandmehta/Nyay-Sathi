# Returned wrong goods, ₹2,800 refund — live evaluation, 20 November 2026

The owner requested the exact Hindi prompt recorded in `hindi-refund-2800-live.actual.json`. One isolated Hindi conversation was created in the latest preview; no complaint was submitted externally, and no secret value was retrieved.

Initial actual result: HTTP 200, 58.49 seconds for the turn (68.71 seconds for health/bootstrap/create/turn). Research route, two timed-out search calls, zero fetched passages; applicability and answer completed but independent review timed out. The safe partial reply suggested a written complaint to the grievance officer and preserved the return/order evidence, but omitted an actionable NCH portal/phone next step and appended an unnecessary withheld-draft notice. **Core routing expectation failed**, despite the Hindi language check passing. Reported tokens: 27,993; actual billed cost unknown.

Reproduction found that the generic Hindi word “शिकायत” added FIR/police retrieval concepts, while wrong-item/return phrasing did not add consumer retrieval concepts. This polluted initial context with criminal-law sources and forced unnecessary web research.

Fix: removed the generic complaint→police expansion; explicit police/FIR wording still expands correctly. Added wrong-goods/return vocabulary to the existing consumer retrieval expansion. A relative score floor drops weak candidates from separate pack lookups while preserving explicitly guaranteed concept matches. These are retrieval changes; the LLM still selects routes and generates answers, and applicability/publication reviews remain enforced.

Regression tests use the exact prompt with real local source retrieval: the current NCH passage must be present and unrelated criminal/BNSS passages absent. A separate test checks that a generic complaint no longer implies police while an explicit police complaint still retrieves FIR concepts. Targeted result: **72 passed**. An initial targeted run caught one remaining weak BNSS hit before the score-floor fix; it was not ignored or marked acceptable.

Initial severity: **8/10**, verified failure to provide the supported consumer complaint route. Action: fix before accepting this scenario; production remains unchanged. Live retest follows in a separate actual-output artifact. Do not infer success from these offline tests.

The wider regression exposed two mapping checks requiring follow-up: an old test explicitly assumed that a context-free “complaint” means police, and an actual mixed harassment/land complaint lost a needed FIR provision. The former expectation was corrected to explicit police-complaint wording; the latter was fixed by retaining contextual complaint-plus-harassment/threat retrieval. The original mixed-land, Hinglish police and jurisdiction tests remain intact. Targeted routing + legal-coverage result after correction: 35 passed, 2 skipped. No publication guard was removed or relaxed.

## Corrected preview live result

Tested code commit `ea4dfcd`, preview https://nyay-sathi-5h38ctxfu-anandmehtaashutosh-6445s-projects.vercel.app/ . The exact same prompt and Hindi setting were used. Actual output is retained in `hindi-refund-2800-fixed-live.actual.json`.

- HTTP 200; 59.18 seconds for the turn, 69.67 seconds for the full cold probe; runner 58.030 seconds.
- Verified route; seven initial passages, no web queries, no research batches.
- Hindi body now gave the platform grievance-officer path, 1915/NCH, and the return/pickup-message and order/payment evidence checklist. It did not claim filing or promise a refund.
- Initial independent review completed and rejected two claims. A targeted repair completed, but its independent rereview timed out. Only already-accepted material was published. **Publication and overall test status remain partial**, not a clean pass. The response did not retain a personalized opening mentioning ₹2,800/three weeks.
- Five reserved calls: router, primary, independent review, repair, repair review. Same selected Sol model/medium configuration; 34,954 reported tokens; actual billed cost unknown.
- Remaining follow-up asked both India applicability and the exact return date in one question. Some official terms stayed in English. No completed draft-follow-up test is claimed.
- Full backend regression after the contextual-police correction: **780 passed, 4 skipped**, five existing dependency warnings. Homepage/colors unchanged; production not promoted.

## Delivery judgment and next actions

**Working slice:** Hindi guidance now identifies an actionable official complaint channel and appropriate evidence, with truthful external-action status. The initial source-selection defect is fixed for this exact scenario, and original mixed harassment/police retrieval checks pass.

**7/10, verified incomplete core response/review:** the deadline prevented repair approval and withheld the personalized primary answer. Preserve the remaining supported assistance; do not mark this scenario fully accepted or promote on this evidence alone. Implementer/next action: fix the answer/review/repair time allocation or constrain optional claims so the core route can complete its independent review. Do not bypass review or silently change the owner's model/reasoning setting. No further paid rerun was made solely to obtain a green result.

**5/10, verified latency degradation:** near-one-minute turn. Same follow-up owner/action as above; measure warm UI behavior when the critical review completion issue is fixed.

**3/10, verified usability issues:** combined follow-up, untranslated official terms and missing personalized opening after withholding. Implementer/next action: defer wording polish until review completion is reliable, then ask one essential question and explain official terms in Hindi.

The inherited `legal_certification` metadata flag is not professional certification; see the earbuds report. The actual JSON, failed initial result, fixes and remaining limitations are all retained. The actual response is not replaced by a hand-written success fixture.
