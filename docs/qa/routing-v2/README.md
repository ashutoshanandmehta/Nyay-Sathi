# Three-level V2 routing implementation — 20 November 2026

Status: implemented and pushed on a separate branch based on the latest GitHub Hindi-homepage baseline; Vercel built a separate preview. This report does not establish live-model quality or production readiness. Existing production is unchanged by this change.

## Implemented behavior

The default primary agent now executes a conditional LangGraph preflight on every turn, then reuses the existing answer, mechanical grounding, independent review, targeted repair and case/draft persistence pipeline.

- Fast: an LLM selects sufficient, applicable existing evidence or a straightforward conversational/draft task. No extra applicability call or mandatory search.
- Verified: an additional structured LLM assessment checks jurisdiction, incident date, source currency and conflicts. Inapplicable passage IDs are excluded from the evidence registry; one essential missing fact can be requested.
- Research: sanitized public questions go through the existing official-source research service, then applicability assessment. A Verified assessment can escalate to Research once during preflight. Unresolved issues remain explicit.
- A later research tool call escalates the displayed route and runs the same applicability gate. Failed assessment discards newly fetched evidence.
- Urgent protective guidance is saved/emitted before the router, including when the router fails.
- Router, applicability, answer, review, repair and search share the existing per-turn request/token/time allowances and telemetry. Review timeout now respects remaining time. Optional strict spend limits still require dated complete pricing; **no approved total live-test spend cap is configured**.
- Default text model: `gpt-5.6-sol`, medium reasoning. Planner inherits review; roleplay inherits chat; official search uses the same default. Audio and embeddings retain specialized models. Environment overrides remain supported. The selected Sol model never silently drops reasoning after rejection.
- The existing widget keeps its styling, shows actual route/escalation events, and no longer claims a linear six-step percentage or legally “Certified” output.
- `frontend/src/App.tsx` and all stylesheet files are unchanged. The approved Hindi homepage and original colors remain.

## Evidence and reproduction

All automated checks used local fixtures, mocked provider transport, or a deliberately unconfigured local server. **Paid calls: zero.** These establish software behavior, not whether an actual LLM makes the correct routing decision or gives accurate legal advice.

- [Recorded scenario outputs](scenarios.actual.json): 15 prompts including ₹5,000 defective earbuds, Hindi/Hinglish, refunds, delivery, services, corrections, dates, location, stale/conflicting sources, misleading claims, banking and unsupported questions. Expected route decisions are injected fixtures, clearly labeled; outputs contain actual executed stages, calls and limitations.
- `PYTHONPATH=backend python scripts/evaluate_routing.py`: 15/15 fixture scenarios recorded.
- Targeted backend checks: `python -m pytest backend/tests/test_agent_routing.py backend/tests/test_primary_agent.py backend/tests/test_primary_provider_transport.py backend/tests/test_practice.py backend/tests/test_search_costs.py backend/tests/test_devspace.py backend/tests/test_answer_quality.py -q` — 152 passed, 1 skipped. Includes real API→runner→message-metadata tests for all three paths, urgent-before-router-failure, exclusions, budget exhaustion, bounded escalation and SDK serialization/model parameters.
- Broader backend regression: 774 passed, 4 skipped, one prompt-size failure. The prompt was reduced to 10,490 characters under the existing 10,500 limit; the affected prompt test and the entire targeted set above then passed. No prompt-size safeguard was weakened.
- Frontend: 47 tests passed, including route escalation and absence of false certification. Production TypeScript/Vite build passed; an existing bundle-size warning remains.
- Eight desktop/mobile browser checks passed; results are recorded in the final verification log alongside this report. These are offline UI checks, not a live conversation quality claim.

Use the project's Python environment with test dependencies and `npm ci` in `frontend`. The local environment symlink used for verification is not committed. Browser config expects `backend/.venv` and deliberately sets an empty API key. No secrets or private conversations are included in these artifacts.

## Defects found and fixes

| Finding | Actual evidence / fix | Remaining impact and next action |
| --- | --- | --- |
| Contact freshness had expired | Initial backend test omitted 112; existing record expired 14 November. Rechecked 112 and 1930 using official sources below; extended only those two records through 27 November. | 3/10: requires periodic source refresh; owner to recheck before expiry. Other specialist contacts remain subject to their existing expiry checks. |
| Hinglish urgent-fraud wording missed early help | “India mein UPI fraud hua, paise abhi kat rahe hain” initially emitted no safety event. Added a narrow Hindi/Hinglish risk cue; API safety-before-router-failure test passes. | 4/10: language-based early detection cannot guarantee every paraphrase. Record misses; retain the model safety tool as another path. |
| Test environment leaked model overrides | Full regression used `gpt-4o` after DevSpace directly wrote an absent environment variable. Fixture now tracks/restores absent variables too. | 0/10 for the reproduced leak; covered by subsequent targeted run. |
| Tests assumed low reasoning | Search/roleplay assertions conflicted with the approved medium setting; assertions updated. Legacy drop-reasoning compatibility test explicitly selects an older model. | 0/10 for those asserted request settings; actual provider access remains unverified. |
| Prompt exceeded existing size limit | Added workflow instruction initially exceeded 10,500 characters. Condensed redundant wording while retaining applicability rule and required constraints. | 0/10 within the checked size/constraint scope. |
| Frontend test timed out under concurrent suites | Homepage unit test timed out at five seconds while backend/browser checks competed for resources; unchanged test passed on the focused frontend rerun. | 2/10: test-environment contention; run heavy suites sequentially. |
| Browser checks assumed English | Existing checks searched “call 112” while preserved homepage selected Hindi. Added matching Hindi text; no product language behavior changed. | See final browser log for executed result. |

## Publication limits and next actions

| Capability / unresolved risk | Impact and severity | Next action / owner |
| --- | --- | --- |
| Actual Sol account access, routing judgment, end-to-end complaint quality, latency and total cost | **7/10, unverified release risk:** offline fixtures cannot establish a usable live three-route journey, especially within the hosted deadline. | Owner supplies an approved total test-spend cap; implementer validates all routes with fictional facts before production promotion. |
| Hosted persistence | **6/10, known architecture limitation:** this Vercel baseline uses temporary SQLite, not verified Supabase storage. A new deployment/instance can lose local continuation state. | Keep durable continuation out of demonstrated claims; separately validate the existing Supabase workstream before migration. No database change in this patch. |
| Current legal coverage | **6/10, scope limitation:** semantic applicability checks do not replace source maintenance or legal editorial review. Unknown dates stay unknown; unsupported claims remain withheld. | Continue official corpus validation; narrow the demonstration to verified cases. |
| Production deployment | No new deployment or production model switch claimed by this report. | Validate the selected model with approved capped billing, then promote the reviewed commit using the existing production authorization. |
| Gmail, Drive, Calendar and filing | Deferred; this patch adds no integrations or external actions. | Preserve existing truthful disabled/unavailable behavior; no autonomous filing. |

Official contact verification evidence (20 November): [MHA ERSS](https://www.mha.gov.in/emergency-response-support-system-erss), [MHA parliamentary answer confirming NCRP and 1930](https://www.mha.gov.in/MHA1/Par2017/pdfs/par2026-pdfs/LS17032026/4118.pdf). Direct fetches of 112.gov.in and the I4C FAQ failed; they were not treated as successful verification. [Selected model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol.md) establishes capability, not access for the owner's project.
