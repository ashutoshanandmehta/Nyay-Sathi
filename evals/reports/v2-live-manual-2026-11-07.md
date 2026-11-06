# V2 manual live evaluation — 7 November 2026

## Scope

- Engine: `primary-agent-v2.0`
- Execution: two prompts, each in a fresh conversation through the real HTTP API
- V1 remained running separately on port 8000; V2 was exercised on port 8200
- Evaluation allowances were not used; normal per-turn request, token and 60-second limits applied
- Cost is unknown because dated pricing was not configured. Token counts below are provider-reported usage, not billing records.

## Defects found and corrected during the run

1. Stateless tool continuation failed with HTTP 400 because the installed SDK exposed the API field `async` as `async_`, and replay used Python attribute names. Response items now serialize with API aliases. A transport-level regression test covers this.
2. Completed calls retained their worst-case token reservation, preventing the mandatory reviewer despite much lower reported usage. Completed reservations now reconcile to reported usage; failed or unknown-usage calls remain conservatively reserved. A budget regression test covers review capacity.

## Final post-fix result: Amazon missing refund

- HTTP status: 200
- End-to-end API time: 60.23 seconds
- Provider calls: 6
- Reported tokens: 44,773
- Research: 1 query; 4 documents attempted; 0 passages published
- Verification: partial; independent review performed
- Outcome: failed the main usefulness gate

The published answer preserved evidence-preparation advice and a limitation, but it did not give the requested next practical step. The first review requested a repair; repair completed, but the mandatory repair review timed out at the 60-second deadline. Unsupported or unre-reviewed claims were correctly withheld.

## Final post-fix result: Goibibo/hotel age-policy dispute

- HTTP status: 200
- End-to-end API time: 48.05 seconds
- Provider calls: 5
- Reported tokens: 38,507
- Research: 2 queries; 4 documents attempted; 0 passages published
- Verification: partial; independent review performed
- Outcome: failed the complete-request gate

The answer usefully identified Goibibo and hotel management as immediate recipients and listed relevant records. It did not draft the requested complaint and did not publish a verified escalation route or source-backed legal proposition. The legal-options task was partial and the drafting task was deferred.

## Release verdict

Both live prompts fail the V2 release acceptance gate. The safety boundary behaved correctly: rejected, unsupported or unre-reviewed content was withheld. The product-quality boundary did not pass because neither prompt received a complete, actionable answer.

Next engineering priorities are:

1. Improve official-source acquisition/selection and expose fetch limitations in persisted diagnostics.
2. Reserve sufficient wall-clock time for repair plus mandatory re-review, or stop before repair and publish the useful reviewed subset without implying completion.
3. Ensure factual complaint drafts grounded in the user's own record can pass review without inventing legal propositions.
4. Re-run these exact prompts after those changes and require actionable route, requested draft, published source provenance where legally needed, and no fallback limitation appended to an otherwise complete answer.
