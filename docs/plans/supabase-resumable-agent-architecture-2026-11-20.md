# Nyay Saathi: resumable agent backend on Supabase Free

Architecture proposal for agy, 20 November 2026. Priority: make the Android backend survive long AI reasoning and interrupted connections while preserving retrieval, verification and action controls. This document changes no application code, infrastructure, deployment, model, or paid configuration.

## Decision

Replace the request-bound agent loop with a persisted workflow. Each Edge execution claims and advances a bounded step; long model generation runs through a compatible provider's asynchronous mode. PostgreSQL stores workflow progress, evidence references and publication state. The app reads durable events and reconnects independently of generation.

All application services stay on Supabase. The existing shared Vercel demo stays untouched. AI and Google remain external APIs, as already intended. Do not add a separate Python server or an always-running external worker.

The owner confirmed the Supabase project is on the Free plan. Current documented Edge limits include a 150-second worker lifetime, 150-second request idle timeout, two seconds CPU per request, and 256 MB memory. Async I/O waits do not consume CPU allowance but do consume elapsed worker lifetime. Streaming and `waitUntil` do not remove runtime limits. See [Edge limits](https://supabase.com/docs/guides/functions/limits) and [background task limits](https://supabase.com/docs/guides/functions/background-tasks).

## Current implementation gap

The newer implementation is in agy's separate worktree:

`/Users/ashutoshanand/.gemini/antigravity/worktrees/Nyay Sathi V2/android_supabase_migration_plan`

In that worktree, `supabase/functions/nyay-api/handler.ts` runs up to four primary/tool rounds, semantic review, repair and re-review inside one handler. `openai-provider.ts` defaults to 45 seconds per model call and uses synchronous response collection. Several individually successful calls can exceed one worker's total lifetime.

The research adapter currently searches a local proposition pack. Full hosted vector retrieval and live official-source research must be implemented and measured, not inferred from the existing method names. Google connection/action scaffolding does not yet establish working integrations; see the [implementation review](agy-implementation-review-2026-11-20.md).

## Service layout

```text
Existing React UI bundled in Android
    |
    +-- authenticated command API: admit turn / approve action / cancel
    +-- event/status API: replay events / reconnect / read result
    |
Supabase PostgreSQL
    +-- private cases, facts, documents, permissions
    +-- turn runs, step records, provider references, evidence snapshots
    +-- outbox/queue, leases, deduplication, append-only events
    +-- public legal corpus, versions, jurisdiction metadata, retrieval indexes
    |
Short-lived Edge executors, dispatched through durable work
    +-- local retrieval and applicability
    +-- bounded official-source web research
    +-- async model submission / result collection
    +-- mechanical checks / async semantic review / targeted repair
    +-- approved answer publication / authorized case patches
    +-- separate approved Google actions
```

Use logical stages, not a separate LLM agent or network service for every box. Deterministic routing, authorization, hashes, IDs and exact source checks belong in code.

## Request and execution lifecycle

1. **Admit:** verify the caller and case ownership, validate input, atomically reserve request/spend budget, store the request payload hash, create the run and enqueue its first step. Return the run reference promptly. A retry with the same request and payload reuses the run; a changed payload conflicts.
2. **Prepare context:** load a minimal case snapshot, consented evidence, confirmed region and incident date. Emit any independently approved urgent safety guidance through the existing safety rules. Save the context version/hash.
3. **Retrieve:** search the legal corpus using metadata filters plus lexical/vector retrieval where configured. Select applicable national/state material, definitions, exceptions and temporal versions. Save source identifiers and passage provenance.
4. **Submit generation:** create a persisted submission intent, submit using supported provider background processing, save the response reference and mark the step as waiting. Return without sleeping until the model completes.
5. **Collect:** a verified webhook or a later short polling execution checks that same response. Pending work is rescheduled with backoff; completed output is runtime-validated and stored before advancing.
6. **Execute tools when requested:** validate allowed tool names and arguments, run bounded retrieval/research reads, persist results, and submit the next model continuation. Preserve required provider continuation items; do not restart generation from only the latest user message.
7. **Verify:** perform deterministic citation/applicability/dependency checks. Submit semantic review as another resumable provider step. Reject missing, duplicate or contradictory claim verdicts. Repair only rejected material, then recheck affected dependencies and coherence.
8. **Publish:** atomically persist approved answer blocks, authorized case changes and final events. An accepted answer does not automatically authorize every proposed case update. Reconnects replay published events without rerunning inference.

Suggested run states:

```text
queued → preparing → retrieving → generation_pending
       → tools_pending → generation_pending
       → checking → review_pending → repair_pending → checking
       → publishing → completed

Any appropriate stage → awaiting_user / retry_scheduled / failed / cancelled
```

Each transition needs a persisted step ID, input version/hash, attempt count, lease generation, and recorded output. Existing turn/event infrastructure should be extended rather than replaced blindly with parallel tables.

## Durable dispatch and recovery

- Use Supabase Queues or a transactional PostgreSQL outbox, with an authenticated Edge consumer. Select and test one mechanism for the prototype. Persist state changes and enqueue intent atomically.
- Use provider completion webhooks for prompt continuation, with signature verification and delivery deduplication. Use a scheduled bounded sweep for lost webhooks and pending work. The app may request an authorized status refresh but must not be the only execution driver.
- Cron/Queues scheduling and service availability must be verified on the actual target project. Do not recursively call workers forever or use a minute-long in-process sleep as a scheduler.
- Each worker claims a lease and advances a small amount of work, then exits. A proposed development target is a maximum 30–60 seconds of work per execution, leaving margin below the platform ceiling; this is a design budget, not a measured guarantee. Worker reuse, CPU and memory limits still require recovery.
- Network operations have individual deadlines and input/output limits. If the next operation cannot fit the remaining budget, persist and reschedule it. Heavy OCR/extraction must use a separately validated bounded approach; naming it a job does not make it fit.
- Fence stale workers with lease generation checks on all publications and trusted state changes. A crashed worker's lease can expire; its successor resumes a stored step rather than repeating the entire conversation.
- Acknowledge queue delivery only after durable transition/output storage. Design for repeated delivery and verify deduplication at each externally visible operation.
- Provider submission has an ambiguous-outcome window: a request may be accepted before its response ID is saved. Record intent/correlation before submission and reconcile through supported provider evidence. Do not assume an unsupported exactly-once API or automatically start another billable generation.

References: [Supabase Queues](https://supabase.com/docs/guides/queues), [Edge queue consumers](https://supabase.com/docs/guides/queues/consuming-messages-with-edge-functions), [Cron](https://supabase.com/docs/guides/cron).

## Long model calls and privacy

Implement an async provider interface with submission, status/result retrieval and cancellation. Verify support for the selected model, structured output and tools before enabling it. The currently configured model must not be assumed to support the desired behavior merely because the API accepts ordinary requests.

OpenAI's documented background mode permits later retrieval and webhook-driven continuation. The current documentation says response data is temporarily stored even with `store: false`; therefore retaining that flag alone is not a promise of no provider-side storage. Review the applicable retention controls, minimize uploaded case data and accurately disclose the behavior. Do not silently change the product's privacy contract or run paid evaluation calls without an agreed budget.

Keep local checkpoints sufficient to resume when provider retrieval expires, consistent with privacy/retention requirements. Preserve required opaque continuation data securely; do not expose hidden reasoning through user-visible events. If the chosen provider/model cannot support long asynchronous generation under acceptable data controls, that is an explicit architecture constraint to resolve rather than pretending ordinary HTTP can run indefinitely.

Reference: [OpenAI background processing](https://developers.openai.com/api/docs/guides/background).

## Retrieval, JSON rules and fresh research

Ingestion is separate from live answering. Store reviewed public legal documents and structured rules with source URL, provision locator, jurisdiction, effective interval, amendment/supersession relations, ingestion version and review state. A JSON file's existence is not evidence of legal authority or freshness.

For each turn:

- Use confirmed case facts and date/region to construct retrieval filters. Include relevant national law as well as regional material; do not filter out national law simply because a state is specified.
- Combine lexical and vector results where available, deduplicate, expand definitions/exceptions and rerank a bounded candidate set. Benchmark the chosen PostgreSQL indexes and actual corpus; selected local propositions are not a complete vector database.
- Trigger web research for missing support, stale material, conflicts or a fresh official procedure/contact need. A database hit does not automatically mean sufficient evidence; a search snippet does not establish a legal proposition.
- Search using a configured real provider and fetch a bounded number of official sources with safe URL handling, size/time limits, source dates and provenance. Block private-network/credential destinations and treat page content as untrusted data.
- Save the evidence used for verification with permitted retention. If authoritative support cannot be obtained, qualify or withhold the affected claim. Do not fill the gap with confident wording.

Independent reads may run concurrently when they do not depend on one another. Avoid parallel writes to shared case state, and do not run web search on every request just to make the workflow look more agentic.

## Google tools and location

Expose controlled application tools for Drive, Gmail, Calendar, reverse geocoding and Places. Direct Google APIs are sufficient; adding an MCP server is optional and does not bypass OAuth, timing, ownership or approval requirements. Developer-chat Google connections do not authorize customer accounts in the product.

Read tools have narrow scopes, bounded results and authenticated ownership checks. Writes are separate durable action jobs. The model may propose a draft/action, but the backend enforces the customer's exact approval and actual provider receipts.

- **Drive:** upload actual original bytes under the customer's connection; retain permitted IDs, hashes and manifests only after provider confirmation. Handle moved/deleted/revoked files truthfully.
- **Gmail read:** customer opt-in, verified scopes, bounded thread import and prompt-injection isolation. Gmail content is evidence, not instructions to the agent.
- **Gmail send:** exact recipient/subject/body/attachment approval hash, atomic dispatch reservation, real provider call and receipt. Any edited payload invalidates approval. An ambiguous timeout requires reconciliation; never blindly resend. Sending email is distinct from official filing or a confirmed remedy.
- **Calendar:** use a narrow optional connection, initially evaluating a dedicated app-created calendar for approved reminders/follow-ups. Preview date, time zone, title, description and attendees before writing. Require real event receipts and reconcile ambiguous writes; event creation is not proof that a legal deadline is correct.
- **Location:** obtain device position through Android permission, suggest a region through geocoding, and let the customer confirm/edit. Keep current position separate from incident location and case jurisdiction.
- **Nearby offices:** Places can discover candidates; verify competence, official destination and procedure separately. Do not label a Maps listing as a verified legal authority merely because it is nearby.

Run an authorized file upload or email send independently from answer generation unless the answer genuinely needs its result. Optional Google features must not block ordinary questions.

See [Google services and location setup](google-services-setup-2026-11-20.md).

## Streaming without weakening quality

Separate execution from delivery. Persist ordered events for accepted, retrieving, researching, waiting for model, verifying, approved blocks, awaiting approval and terminal outcome. The UI shows truthful progress, not invented reasoning text or percentages.

Use reconnectable SSE with a bounded connection lifetime, or polling initially. Reconnect using the last persisted sequence. Ending a delivery connection does not cancel the run. Authorize every event read and filter unpublished/superseded content.

For the first prototype, publish the reviewed answer after complete verification while showing immediate progress and approved safety guidance. Later, evaluate block-by-block review only where cross-block dependencies and contradictions remain controlled. Token streaming of an unreviewed candidate is not equivalent to approved answer streaming.

Record time to acceptance, first useful safe content, first approved answer block, and completion separately. Async orchestration improves survivability; it does not itself make the model reason faster or prove answer quality is unchanged.

## Implementation sequence and recruiter gate

Google-only Android onboarding is an explicit prototype milestone: Welcome → Continue with Google → confirm available profile/language → optional Drive/Gmail/Calendar/location cards → truthful setup summary → Home. Preserve denied-feature fallbacks and returning-session behavior; do not assume Google login grants service access or date of birth. This replaces guest-first onboarding as the Android product target while preserving existing data through a tested path where necessary. See [shared checklist and parallel ownership boundaries](../../checklist.md).

1. Correct the known real-response parser, Google false-success and PDF/extraction defects. Preserve the existing demo and worktrees.
2. Refactor the current handler into persisted step functions; implement transactional admission, outbox/queue and one bounded consumer.
3. Add async primary generation, result collection, webhook verification and scheduled recovery. Test tools/continuations before adapting review and repair to the same pattern.
4. Wire frontend task admission, status/events, reconnect and cancellation. Retain the current UI.
5. Connect evaluated legal retrieval and real bounded official-source research, then actual Google tools as separately testable capabilities.
6. Deploy only to the Nyay Saathi Supabase project after code correction and controlled checks. Install and test the Android prototype.

Required evidence before declaring the backend demo-ready:

- A workflow lasting more than 200 seconds completes while each Edge execution stays within its budget; use a delayed test provider first, clearly marked as infrastructure testing, then an authorized real-provider check.
- Kill an executor between stages; progress resumes without lost state or duplicate publication.
- Deliver duplicate queue messages/webhooks, disconnect/reopen the app, and retry the original request; the same task resumes.
- Verify owner isolation for jobs, evidence, provider references, events and actions.
- A stale worker cannot publish; cancellation wins against late completion.
- Primary/tool/review/repair fixtures use faithful raw HTTP responses, including malformed, refused and incomplete output.
- Citation/version/jurisdiction failures prevent unsupported publication. Compare representative answer quality with the existing web backend; do not assume parity.
- Missing OAuth, revoked tokens, provider failures and ambiguous sends never create false success.
- Record hosted runtime, latency, usage and recovery results separately from offline test passes. Background AI remains billable and free-tier quotas still apply.

The first engineering deliverable is a resumable, verified answer pipeline. Google services and broader domains attach to that foundation; they must not become prerequisites for proving that a long turn survives.
