# V2 runtime architecture

The default `PrimaryAgent` replaces the fixed graph's separate interpretation, ordinary intake and planning calls. The inherited graph remains selectable with `ASSISTANT_ENGINE=legacy`. The API still calls the same `invoke(state, thread_id, progress)` interface and uses the existing durable reviewed-result/commit/finalize protocol. Here, the historical database status `reviewed` means publication checks completed; exact quotes/templates need not have had an independent LLM reviewer. Metadata records the actual review performed.

## Modules

- `app/agent/contracts.py`: closed Pydantic contracts for final tasks, claims, research questions, review and patch proposals.
- `provider.py`: installed OpenAI Responses SDK, strict output/tool schemas, stateless continuation with encrypted reasoning items, no hidden retries, explicit output cap and incomplete/refusal handling.
- `runner.py`: bounded primary session, research dispatch, claim checks, optional reviewer, one targeted repair, preservation of unchanged approved claims and final response adapter.
- `research.py`: public-query validation, concurrent discovery, canonical/content deduplication, host-grouped safe fetch, issue relevance/authority ranking, exact extracted passages, scoped snapshots and persistent public cache.
- `budget.py`: atomic shared request and conservative token/spend reservations across concurrent discovery and model continuations, deadlines, reported usage and nullable monetary estimates.
- `verification.py`: mechanical identity/provenance/dependency checks, exact attributed private extracts, approved low-risk templates and escalation of all original prose for independent review.
- `safety.py`: approved language-specific protective guidance, maintained emergency contact reference, early trigger and model-requestable safety tool.
- `workflow.py`: actual engine definition used by the existing workflow drawer.

## One logical session, multiple requests

The primary model can return one `research_legal_issue` tool call containing one or two independent public questions. Runtime validates them, reserves continuation/review capacity, looks for unexpired query evidence, adds relevant saved corpus candidates and executes permitted search queries concurrently. Selected public documents are downloaded with V1's DNS/IP/redirect/TLS protections. Different hosts overlap; a host's downloads are sequential. The exact tool output is supplied in a continuation with the original reasoning/tool-call items.

There are at most two research batches and three primary rounds, including any repair round. The second batch must name a material gap. Repeated normalized query hashes are rejected. Cached acquisition does not establish current law, court treatment or case applicability. Candidate and tool limits are ceilings, not source quotas.

The inherited search provider itself uses OpenAI web search and incurs a provider request. Its source enumeration is parsed for URLs; fetched underlying text, rather than a snippet, supports claims. By default the entire runner has six provider-request slots. A two-query batch plus two primary rounds and a reviewer can consume five requests before repair. A repair that cannot fit is skipped and unresolved claims stay qualified/withheld.

## Review and publication

Exact private extracts and approved application templates are mechanically validated. Every other generated sentence—including factual paraphrases, drafts, questions and recommendations—currently takes the conservative independent-review path. This deliberately does not assume that a claim label proves its meaning. A reviewer must explicitly mark claims requiring external support; the runtime insists on actual public passage IDs for those claims. Declared legal/procedural/safety claims always need public support.

The reviewer gets the original question and evidence. Duplicate/missing verdicts do not approve a claim. Fresh rejections supersede prior approvals; failed re-review preserves only support for unchanged claims. Dependencies are resolved without accepting cycles. Unsupported parts do not erase supported preparation, but an artifact with a rejected required document claim is not saved as a clean draft.

No model agreement is labelled legal certification. The legacy `passed` and `publication_safe` fields retain API compatibility and refer only to published content. Claim-check metadata distinguishes exact-extract/template checks from independent semantic review. Source title/locator comes from the evidence registry. Free-prose URLs, fabricated source IDs and claims of executing external actions fail validation.

## Case state

The primary session proposes tasks and optional `CasePatch` records alongside the answer. It does not write memory. The inherited `WorkflowPolicy`, `PatchEngine` and `CaseStateManager` check task/case association, current message/document provenance, independent patch support, explicit corrections and optimistic versions. Public law cannot establish private case facts. Uncertain proposals stay staged.

Conversation history is saved for general questions, while case facts/version remain unchanged. One existing conversation still has one active case. The prompt requires unrelated disputes to stay separate even in the same domain; semantically difficult case association remains a model-quality evaluation area. No new multi-case screen was introduced.

Turn receipts, artifact IDs and patch audits survive retries. A changed payload under an existing request ID is rejected. A committed turn can finalize without re-running models or re-applying patches. Existing ownership, CSRF, attachment scope and case-version conflict tests continue to run.

## Safety delivery

Clear imminent-danger wording triggers approved protective text before model/research work. The agent can request `emit_safety` for less obvious urgent inputs. Phone contacts appear only when India is established by the current text or a stored country fact and the maintained reference is within its revalidation window. Expiry suppresses the number, not generic protective guidance.

Safety text is inserted into `turn_safety` before the `safety` SSE event. It survives a failed model call, stream disconnect or reload. The frontend handles fragmented safety frames using the existing chat component and deduplicates against final answer metadata by request/content ID. Consequential free legal text is buffered until verification.

## Storage and cache

V2 has fresh runtime paths; no V1 credentials, owner tokens, attachments or user databases were copied. New tables are additive and created idempotently: `turn_safety` is conversation-owned and cascades on deletion; `public_evidence_cache` stores sanitized-query hashes and public fetched passages with schema version, acquisition/check time and expiry. It never accepts private-origin entries.

The current cache is an evidence accelerator, not a curated current-law service or legal proposition validator. Revalidation is query/TTL based; automatic citator checks and amendment detection are not implemented. Use `python -m scripts.manage_evidence_cache status` or `invalidate`. Invalidation marks entries expired and preserves records.

Saved corpus candidates are used only when recent and relevant. Original source limitations remain visible. Public PDF extraction is bounded to configured pages and explicitly marks omitted pages rather than silently claiming complete extraction. Private attachment page limits remain unchanged. `services/pdf_backend.py` isolates the retained PDF engine.

## Accounting and limits

`AGENT_MAX_REQUESTS=6`, `AGENT_MAX_ROUNDS=3`, `AGENT_MAX_BATCHES=2`, `AGENT_MAX_QUERIES=3`, `AGENT_MAX_DOCUMENTS=6`, `AGENT_MAX_PASSAGES=5`, `AGENT_DEADLINE_SECONDS=60`, and `AGENT_RESEARCH_SECONDS=20` are initial defaults. No automatic retry is performed. Socket operations receive remaining timeouts; the synchronous SDK and network stack still need live deadline characterization.

`AGENT_MAX_TOKENS=160000` is enforced with conservative cumulative reservations based on serialized input bytes/schema/tool definitions plus maximum outputs; reported tokens are separately recorded. Discovery reserves additional provider-context allowance. This can stop optional work before actual token use reaches the limit. It is a resource guard, not exact prebilling.

With `AGENT_MAX_COST_USD` configured, every model needs a non-empty dated `AGENT_PRICING` entry with `input_per_million` and `output_per_million`; discovery also needs `search_per_call`. Optional `cached_input_per_million` refines post-response estimates. Unknown pricing blocks capped work. A timeout or missing usage makes total estimated cost null while preserving known subtotal and conservative reserved amount. Provider actual billed cost remains null. Search-managed context and future pricing changes mean projected caps are not a provider billing guarantee.

Runner metrics record model/review/research timing, first approved guidance, total runner duration and accounting completeness. Their timing scope explicitly excludes API authorization and final commit. Telemetry records contain IDs, counts, timings and error types, never prompts or private document text. The separately stored user transcript and scoped evidence are application records, not anonymous telemetry.

## API and frontend compatibility

All conversation, turn, attachment, draft, export and voice endpoints are retained. SSE adds `safety` to the existing `progress/result/error` events. `Detail.safety_messages` and message metadata add optional fields. Frontend styles are byte-for-byte identical to V1. The workflow drawer renders the new engine definition without requiring legacy node IDs. The legacy drawer remains available for comparison runs.

See [implementation status](v2-implementation-status.md) for what was executed and what is still unverified.
