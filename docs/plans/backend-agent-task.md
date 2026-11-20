# Backend & Agent Integration

Owner: the dedicated Codex chat named **Backend & Agent Integration**, opened by the product owner in the Nyay Saathi V2 project. Assigned 20 November 2026. Status: task brief ready; this coordinating chat has not created, renamed or started another chat.

## Objective

Implement a resumable Android agent backend on the confirmed Supabase Free plan. An overall turn may exceed 150 seconds while individual Edge executions remain bounded and recoverable. Retain source-grounding, verification, authorized case writes and truthful progress. Keep the existing React UI and shared Vercel demo protected.

Read [checklist.md](../../checklist.md), [the complete resumable architecture](supabase-resumable-agent-architecture-2026-11-20.md), [the implementation review](agy-implementation-review-2026-11-20.md), and [the legal retrieval task](legal-knowledge-task.md). These files contain the context required to start without assuming access to the coordinating conversation.

## Baseline and safety of parallel edits

Primary project: `/Users/ashutoshanand/Downloads/Nyay Sathi V2`, branch `codex/android-supabase`.

Newer Round 2 implementation: `/Users/ashutoshanand/.gemini/antigravity/worktrees/Nyay Sathi V2/android_supabase_migration_plan`, branch `android_supabase_migration_plan`.

Both currently contain uncommitted changes. Inventory and compare them before coding. Preserve user work; do not reset, clean or blindly overwrite either tree. Prefer an isolated backend worktree with a carefully established baseline containing the needed newer implementation. Creating a worktree from committed HEAD alone will omit the uncommitted application and planning files; copy/checkpoint only the agreed baseline, without secrets, and verify the result.

Two chats using the same folder edit the same files. Agree ownership before parallel edits to contracts, migrations or frontend API code. This task owns agent transport/orchestration, durable task/event execution, backend wiring and its tests. Antigravity owns public legal content/ingestion/retrieval. Google-only onboarding is approved scope but a separate workstream; do not assume its UI is already implemented.

## Implementation order

1. Reproduce and correct actual Responses API parsing and runtime-validation defects using faithful HTTP fixtures. The current adapter has a 45-second per-call timeout and collects synchronous outputs.
2. Extract the existing request-bound primary/tool/review/repair pipeline into checkpointed step functions, retaining existing authorization and verification invariants.
3. Implement transactional admission, durable outbox/queue, bounded step claims, lease-generation fencing, cancellation and persisted event replay.
4. Add a provider interface for supported asynchronous submission, collection, continuation and cancellation. Verify selected model/tool/schema support and provider temporary-storage implications. Do not assume current `store: false` makes background processing storage-free.
5. Add verified completion webhooks and bounded scheduled recovery. Do not run a long polling loop in one Edge worker or rely on the app staying open.
6. Implement independent resumable review/repair and atomic approved publication/case updates. Keep progress separate from unreviewed candidate text.
7. Wire the current frontend transport to accepted tasks, status/events, reconnect and cancellation with minimal UI change. Consume the agreed legal retrieval fixtures first, then integrate Antigravity's real component through the same interface.

## Existing blockers and scope

The implementation review records false-success Drive/Gmail handlers and PDF/export/extraction defects. Do not enable or advertise them as working. Coordinate ownership of fixes; fail explicitly when an actual provider adapter is unavailable. Real web research is not currently established by the local-pack research method.

Android's approved target is Google-only login, profile confirmation, optional Drive/Gmail/Calendar/location cards, summary and Home. Preserve existing account-owned data during any later transition. Google connection does not grant blanket action approval; device location is not Maps OAuth. Keep these interfaces compatible without expanding this task into all onboarding and Google feature work.

Target Supabase project only: `daojcrxjjkqoirqbvhjn`. Do not touch Riva (`casmdqfgxoihjisrjsbk`). Preserve Vercel configuration, environment and deployment branch. No separate app server, unapproved infrastructure upgrade, or unbudgeted paid evaluation calls. Prepare migrations/deployment artifacts, with verification evidence; do not report a hosted deployment that has not occurred.

## First acceptance milestone

- A delayed-provider infrastructure test drives a task beyond 200 seconds overall through separate bounded executions. Clearly label test doubles; a real-provider check requires its own authorized configuration and spend bounds.
- Worker interruption, duplicate queue/webhook delivery, app reconnection and same-request retries resume the same task without duplicate publication or blind provider resubmission.
- Stale workers cannot commit; cancellation and owner isolation work.
- Primary/tool/review/repair behavior handles real wire formats, refusals, incomplete and malformed results. Unsupported claims cannot pass publication.
- Existing relevant tests/build plus new meaningful boundary regressions pass. Report exact commands/results and unresolved gaps; preserve earlier counts as historical evidence.

Update this task's entries in the shared checklist with evidence and status. Ownership assignment is not proof that implementation or hosted verification has begun.
