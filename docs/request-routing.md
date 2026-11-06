# Independent request interpretation and task workflows

Implemented 6 November 2026. Live model/search validation of this increment is **not run**, at the user's request to preserve API credit.

## Execution flow

1. The API checks owner, CSRF, case, idempotency and the turn lock. It loads authorized memory/version, recent transcript, pending questions, evidence and IST runtime context.
2. `ContextualInterpreter` runs before intake. The read-only `request-v1` contract contains up to eight tasks: exact message excerpts, intent, relationship, entity mentions, domain, case relevance, risk, uncertainty and optional public research questions. It has no database/retrieval/write tools. Owner/case IDs are excluded from the model contract.
3. `WorkflowPolicy` evaluates each task. Update flags only propose changes. Domain consistency, existing/new-case relevance, task type and confirmation scope determine whether intake is allowed. Failed interpretation is uncertain and read-only.
4. Relevant task excerpts can reach fact investigation and staging independently of permission to commit. Hotel/brand words no longer determine domain. The offline relational fallback is explicitly labelled, not presented as semantic model performance.
5. Consumer tasks may use approved-corpus retrieval, consumer playbooks and preparation policies. Other legal tasks use bounded research/handoff. Unrelated tasks receive no complaint plan. Entity/profile discovery is not eligibility proof.
6. `execute_tasks` prioritizes urgent tasks and independently routes general, safety, legal and public-research requests within a shared turn budget. No external submission/send/sign capability exists.
7. The production path now uses task-scoped candidate units and canonical claim-to-evidence IDs rather than a single publish-or-reject response envelope. See [unit publication](answer-unit-publication.md).
8. Independent batched review assesses claim support, task completion and case updates separately. At most one correction/re-review fits the budget. The deterministic composer retains independently approved content while withholding affected claims/dependencies; model agreement cannot bypass hard checks.
9. `CaseStateManager` validates the memory transition and provenance under trusted runtime scope. SQLite atomically checks the base version, commits memory/audit events and marks materially dependent drafts stale. Rejected/concurrent updates roll back. Unrelated turns preserve case memory and edited drafts.

## Interfaces

| Component | Responsibility |
|---|---|
| `RequestInterpretation`, `TaskIntent`, `EntityMention` | Versioned strict contract, unique task IDs and exact source spans |
| `Interpreter` / `ContextualInterpreter` | Injectable read-only structured interpretation |
| `WorkflowPolicy` | Per-task workflow and case-update policy |
| `CapabilityRegistry` | Actual adapter configuration and remaining budget |
| `EntityResolver` | Mention/profile matching; unfamiliar entities stay unverified |
| `TaskResearchService` | Public task research through existing search/fetch/snapshot components |
| `PublicQueryPolicy` | Reject identifiers, private case facts/names and copied evidence phrases |
| `CaseUpdateProposal`, `CaseStateManager` | Proposed transition, consistency/provenance checks and transactional commit |
| `ExecutionValidator` | Coverage, execution claims, eligibility, date arithmetic and mandatory fields |

The modular monolith, SQLite, Chroma, anonymous ownership and lockfiles are preserved. No new package, microservice or per-company agent was introduced.

## Source and legal boundaries

Network permission and source authority are separate. Approved-corpus ingestion retains its official-host allowlist. The new task-research fetch adapter can read discovered public HTTPS destinations with redirect checks, public IP pinning, Host/SNI preservation, private-network rejection, size/page limits and timeouts. It cannot read local files or execute page instructions. Unverified public pages remain candidates; government origin still requires applicability review. Snippets are never supporting passages.

Passages retain URL, text, locator, hash and retrieval time. Unknown jurisdiction/publication/effective dates stay null. Organization and authority discovery cannot establish filing eligibility. Existing consumer policies explicitly assess **preparation**, not full filing admissibility. An `eligible_destination` declaration requires a filing-verified policy and matching passages, jurisdiction and effective dates. Incomplete policies permit preparation/candidate guidance.

Calendar arithmetic is independently checked. No case-specific statutory deadline calculator is validated in this increment; calculated statutory claims are rejected. General sourced timing explanations still require citation and semantic review. Missing mandatory fields or material contradictions prevent send-ready declarations while allowing provisional drafting.

## Limits and observability

Runtime outcomes distinguish disabled, configuration required, policy restricted, budget exhausted, execution failed, no supporting results and succeeded. A configured available adapter is not a claim of verified account/model access. Provider events and fetched snapshots determine execution success.

Defaults: up to eight tasks, two public searches, three documents and eight logical model calls per turn. Interpreter/intake/generation/review clients use zero automatic transport retries; one application-level correction remains possible within budget. Research preserves generation/review capacity. Usage/latency are recorded where available; failed responses may omit usage. Counters are not a billing statement or complete embedding-cost accounting.

`REQUESTS_PER_MINUTE` defaults to 120. The isolated Playwright server uses 600 because its full suite shares one localhost IP; production configuration is unchanged.

## Limitations

See the [executed report](../evals/reports/request-routing-2026-11-06.md). Offline routing matches/latency describe synthetic contracts only. Semantic model accuracy, new general research and uncertain-premise answering were not live-validated. Query privacy checks are defensive, not proof of perfect anonymization. Non-consumer eligibility, complex filing procedures, authenticated platform flows and lawyer review remain bounded or pending. No clinical/veterinary expertise or production/legal-performance claim is made.
