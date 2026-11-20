# Returned wrong goods, ₹2,800 refund — live evaluation, 20 November 2026

The owner requested the exact Hindi prompt recorded in `hindi-refund-2800-live.actual.json`. One isolated Hindi conversation was created in the latest preview; no complaint was submitted externally, and no secret value was retrieved.

Initial actual result: HTTP 200, 58.49 seconds for the turn (68.71 seconds for health/bootstrap/create/turn). Research route, two timed-out search calls, zero fetched passages; applicability and answer completed but independent review timed out. The safe partial reply suggested a written complaint to the grievance officer and preserved the return/order evidence, but omitted an actionable NCH portal/phone next step and appended an unnecessary withheld-draft notice. **Core routing expectation failed**, despite the Hindi language check passing. Reported tokens: 27,993; actual billed cost unknown.

Reproduction found that the generic Hindi word “शिकायत” added FIR/police retrieval concepts, while wrong-item/return phrasing did not add consumer retrieval concepts. This polluted initial context with criminal-law sources and forced unnecessary web research.

Fix: removed the generic complaint→police expansion; explicit police/FIR wording still expands correctly. Added wrong-goods/return vocabulary to the existing consumer retrieval expansion. A relative score floor drops weak candidates from separate pack lookups while preserving explicitly guaranteed concept matches. These are retrieval changes; the LLM still selects routes and generates answers, and applicability/publication reviews remain enforced.

Regression tests use the exact prompt with real local source retrieval: the current NCH passage must be present and unrelated criminal/BNSS passages absent. A separate test checks that a generic complaint no longer implies police while an explicit police complaint still retrieves FIR concepts. Targeted result: **72 passed**. An initial targeted run caught one remaining weak BNSS hit before the score-floor fix; it was not ignored or marked acceptable.

Initial severity: **8/10**, verified failure to provide the supported consumer complaint route. Action: fix before accepting this scenario; production remains unchanged. Live retest follows in a separate actual-output artifact. Do not infer success from these offline tests.

The wider regression exposed two mapping checks requiring follow-up: an old test explicitly assumed that a context-free “complaint” means police, and an actual mixed harassment/land complaint lost a needed FIR provision. The former expectation was corrected to explicit police-complaint wording; the latter was fixed by retaining contextual complaint-plus-harassment/threat retrieval. The original mixed-land, Hinglish police and jurisdiction tests remain intact. Targeted routing + legal-coverage result after correction: 35 passed, 2 skipped. No publication guard was removed or relaxed.
