# Nyay Saathi working agreements

## Delivery attitude — owner decision, 20 November 2026

Build a useful MVP with bounded effort. Completion is based on impact and the main customer journey, not a percentage of passing tests or perfection.

- Finish the requested working slice before optional polish, generalization or unrelated refactoring.
- Classify failures by impact. Block acceptance for broken core flows, authorization/owner isolation, data loss, uncontrolled spending, unsupported legal publication, unauthorized external actions, or false success receipts.
- After two focused attempts on a non-critical failure, record its reproduction, user impact, evidence and follow-up in the checklist/backlog, then continue. Do not keep iterating on cosmetic defects, rare optional edge cases or incidental environment failures.
- If an important feature is unavailable, keep it truthfully disabled or narrow the demonstrated scope and continue independent work. Do not claim the unavailable feature is complete.
- Run targeted checks for changed behavior and one appropriate regression pass. Repeat or broaden only for a material new change, actionable failure or unresolved critical risk.
- Separate test-environment timeouts from product defects. Record unverified checks honestly; never delete, weaken or bypass safeguards merely to obtain green tests.
- Report what works, critical blockers, deferred non-critical issues and the next useful step. Avoid invented completion percentages and endless cleanup loops.
- Preserve existing user changes, worktree ownership and the protected Vercel demo. Consult checklist.md and the assigned task brief for scope.
- Preserve the owner's existing Git identity and repository ownership. Never add ChatGPT, Codex, OpenAI or another AI account as a collaborator, author, co-author, signer or commit trailer; do not add AI `Co-authored-by` metadata when committing or pushing.

## Required delivery report

For each meaningful change or unresolved issue, report: what changed, user/operational implications, verification evidence, residual issue, severity score out of 10 with a brief reason, and next action (fix now, disable affected capability, or defer).

Scores describe remaining impact in the intended release, not the amount of work or the desirability of the change. They are engineering judgments, not measured probabilities or CVSS scores. Distinguish verified defects from unverified risks; never invent confidence.

- 9–10 Critical: privacy/authorization breach, data loss, uncontrolled spending or unauthorized external actions. Block the affected release/capability.
- 7–8 High: broken core journey, materially unsupported legal publication or false action receipts. Fix or truthfully disable before accepting that capability; continue independent work.
- 4–6 Medium: limited degradation with a safe workaround. Record and generally defer if the main journey and important safeguards remain intact.
- 1–3 Low: cosmetic, minor usability or rare benign edge case. Record and move on after bounded effort.
- 0: no known remaining issue for the explicitly verified scope; never use zero to hide an unperformed check.

Keep the report short. Every deferred issue needs its implication, evidence, owner/next step and severity; do not keep retrying it merely to reach a perfect score.


