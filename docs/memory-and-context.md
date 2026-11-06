# State memory and context

The [task-scoped publication increment](answer-unit-publication.md) adds separate candidate/verified claims, immutable evidence bindings and turn-local review caches to working state. Relevant fact proposals can be staged in `staged_case_updates` without overwriting saved memory. Context now includes the latest editable drafts for conversational revisions. Unrelated turns and failed reviews preserve the existing committed case and user-edited drafts.

Nyay Saathi keeps seven distinct layers so conversation convenience does not turn prior assistant prose or application guidance into legal authority.

1. The complete transcript is immutable application history in SQLite, with status, timestamps, attachment IDs, sources, and request IDs.
2. LangGraph working state contains the current intent, latest explicit-request plan, internal coverage statuses, scope, urgency, rewritten query, retrieved passages, feedback findings, revision count, verification result, and call usage. It is checkpointed by owner and conversation thread.
3. Structured case memory stores typed facts, prior values, provenance, contradictions, unknowns, completed actions, pending questions, latest proposed fact keys, options, outcomes, and stale draft IDs.
4. The rolling summary is derived from structured memory. It preserves fact status and unresolved contradictions; it does not convert suggestions into completed actions.
5. Language is conversation-scoped. Sensitive facts are never copied between conversations.
6. Legal-source passages live in an approved public corpus separate from personal evidence. Assistant messages are never indexed as law.
7. Versioned shared playbooks contain intake questions, evidence meaning, explicit route inputs/exceptions, templates, escalation, and lawyer-preparation guidance. They are labelled application guidance pending Indian-lawyer review and are not legal authority.

## Storage boundary

The resolution increment adds a typed private `journey`: append-only reported events, submissions, responses, commitments, outcome, satisfaction with provenance, preferences, and versioned preparation recommendations. Corrections link to superseded events without deleting their audit history. Events from one message retain narrative order; missing historical years remain unknown. Reported company targets are explicitly separate from statutory deadlines. Current projections are included in bounded model context; historical recommendation bodies and the full previous draft specification are excluded to avoid context growth. SQLite event/recommendation tables cascade on case deletion. Optimistic version checks reject stale case saves and draft edits.

| Store | Content | Explicit exclusion |
|---|---|---|
| Chroma and BM25 | Approved public legal/procedure passages and selected judgment paragraphs | User facts, uploads, drafts, assistant answers, and playbook routing rules |
| Versioned shared knowledge JSON | Intake/evidence playbooks, route gates, template structures, lawyer questions, referral limits | User case records and any claim of legal authority |
| SQLite case workspace | Objective, parties, locations, facts and provenance, timeline, contradictions, actions, responses, legal-review questions, drafts and versions | Other owners' or conversations' records |
| Private file storage | Original uploads and corrected extracted text | Shared retrieval corpus |
| Source register | Authority, URL, dates, version information, hash/status, and limitations | Retrieval date masquerading as an effective date |

## Context priority

Before every turn, the API—not the model—loads authorised case memory, pending questions, rolling summary, recent messages and private attachments. The context builder adds the current timezone-aware date and time in `Asia/Kolkata`, parties and locations, structured facts with provenance, requested remedy, timeline, completed actions, responses, correspondence, contradictions, unknowns, urgent matters, up to ten recent turns, and the five most lexically relevant case-scoped evidence excerpts. It removes oldest recent turns until the configured character budget is met. The complete transcript remains stored separately. Current time is labelled as incapable of resolving an ambiguous historical date or determining a legal deadline.

The graph selects only the relevant intake playbook for the issue and supplies a bounded evidence guide to intake/response prompts. A playbook may choose up to two unanswered questions—for example, a seller's “refund processed” claim branches to processing date and transaction reference—but any substantive legal conclusion still requires newly retrieved approved passages and verification.

Corrections append the previous value, source message, timestamp, and confirmation status. A material value change increments the case version and marks older drafts stale. Natural confirmations such as “Yes, that's right” apply only to the latest proposed fact keys; they do not promote every allegation in the case. A provisional draft may use user-reported facts, but a material contradiction is surfaced as a targeted question or placeholder. Document text remains a document statement until the user confirms the underlying fact.

## Thread ownership

Checkpoint thread IDs combine the server-side anonymous owner ID and conversation UUID. API access still performs an owner lookup; knowing a conversation UUID is insufficient. Deleting a chat removes application rows, files, exports, and the matching LangGraph thread.
