# Hosted checks — 20 November 2026

Implementation commit: `6715260940d15ec0aac09a988bd933cf46509f5a`, pushed as `codex/v2-managed-production`. Follow-up documentation/diagram corrections preserve the same routing implementation.

- [Routing preview](https://nyay-sathi-oj1jcu5q8-anandmehtaashutosh-6445s-projects.vercel.app/): Vercel READY; `/api/health` HTTP 200, status `ok`, engine `primary-agent-v2.1-routed`, `ai_configured=false`.
- [Existing production](https://nyay-sathi-sage.vercel.app/): `/api/health` HTTP 200, status `ok`, engine `primary-agent-v2.0`, `ai_configured=true`. It remains on the existing main-branch deployment; the new routing has not been promoted.
- [Review changes](https://github.com/ashutoshanandmehta/Nyay-Sathi/compare/main...codex/v2-managed-production): branch pushed successfully with the owner's existing Git identity. The GitHub integration rejected draft pull-request creation with HTTP 403 (“Resource not accessible by integration”). No pull request is claimed.

The owner previously scoped the backend key to Production only. No secret value was retrieved or changed. The preview therefore cannot produce a live AI response yet; this is an explicit unavailable capability, not a functioning simulated AI demo. No paid model calls were made during these health checks.

Before promoting routing, validate with fictional consumer/fraud examples under an owner-approved total spending cap and an appropriately scoped backend credential. Confirm model access, response quality, three-route behavior, actual latency and cost. No new approval to alter the already-authorized production target is being inferred as a substitute for those checks.

Remaining severity: 7/10 **unverified core-journey risk** for live routing; keep new routing out of production until tested. PR creation is a 3/10 review-workflow limitation with a working compare-link alternative. Owner provides capped billing; implementer performs live validation and then promotes the reviewed commit under the existing deployment authorization.
