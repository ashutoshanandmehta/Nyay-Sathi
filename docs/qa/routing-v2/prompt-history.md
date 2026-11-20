# Build instructions and runtime prompts

User-approved scope, in order:

1. Reuse V2 as the MVP baseline; preserve original interface/colors and the approved Hindi homepage. Use actual conversational AI rather than deterministic replacement fixtures.
2. Keep owner credentials on the backend. Preserve grounding, privacy, consent and truthful action status. No automatic external filing or unrelated integration expansion.
3. Implement Fast, Verified and Research workflows, with immediate urgent-fraud protection and escalation when evidence requires it.
4. Use GPT-5.6 Sol with medium reasoning across the text-agent paths; route complexity changes work, not model identity.
5. Present the architecture before editing. The architecture was presented; the owner then said “Now go ahead with the plan.”

Runtime prompts actually used by this implementation:

- `backend/app/agent/routing.py`: `ROUTER_PROMPT` and `APPLICABILITY_PROMPT` (exact source text, versioned with the code).
- `backend/app/prompts/primary.md`: existing V2 answer/draft instructions, with a compact requirement to respect workflow limitations and excluded evidence.
- `backend/app/prompts/primary-review.md`: reused independent review prompt, unchanged.
- Existing research public-query validation and strict structured contracts are reused. User documents and source pages remain untrusted data.

The 15 evaluation inputs and actual fixture outputs are retained in `scenarios.actual.json`. They are software orchestration evaluations, not prompts sent to a live model. No API key, private case record, hidden reasoning, or system/developer instruction is recorded here.
