import operator
from typing import Annotated, Any, TypedDict


class LegalAssistantState(TypedDict, total=False):
    request_id: str
    pipeline_version: str
    patch_decisions: list[dict[str, Any]]
    staged_patches: list[dict[str, Any]]
    early_extraction: dict[str, Any]
    extraction_status: str
    call_telemetry: list[dict[str, Any]]
    usage_completeness: str
    assistance_status: str
    document_status: str
    legal_verification_status: str
    owner_id: str
    conversation_id: str
    message_id: str
    current_message: str
    language: str
    context: dict[str, Any]
    memory: dict[str, Any]
    summary: str
    intent: str
    scope: str
    urgent_reason: str | None
    needs_retrieval: bool
    rewritten_query: str
    passages: list[dict[str, Any]]
    research_plan: dict[str, Any]
    research_status: str
    web_sources: list[dict[str, Any]]
    shared_guidance: dict[str, Any]
    intake_questions: list[str]
    request_plan: list[dict[str, Any]]
    request_coverage: list[dict[str, Any]]
    follow_up_questions: list[str]
    response: str
    response_envelope: dict[str, Any]
    feedback_review: dict[str, Any]
    revision_attempts: int
    revision_succeeded: bool
    verification: dict[str, Any]
    token_usage: dict[str, int]
    model_calls: int
    unit_protocol: bool
    base_memory: dict[str, Any]
    base_summary: str
    task_contexts: list[dict[str, Any]]
    candidate_batch: dict[str, Any]
    unit_review: dict[str, Any]
    reviewed_candidate_digest: str
    reviewed_context_digest: str
    verified_claim_reviews: dict[str, Any]
    turn_review_findings: list[dict[str, Any]]
    corpus_version: str
    exposed_evidence_ids: list[str]
    case_diff_review_complete: bool
    case_proposal_task_ids: list[str]
    staged_case_memory: dict[str, Any]
    case_commit_approved: bool
    unit_outcomes: list[dict[str, Any]]
    approved_documents: list[dict[str, Any]]
    published_passage_ids: list[str]
    publication_status: str
    interpretation: dict[str, Any]
    interpretation_status: str
    entity_candidates: list[dict[str, Any]]
    task_plan: list[dict[str, Any]]
    tool_records: list[dict[str, Any]]
    capabilities: dict[str, Any]
    case_task_ids: list[str]
    case_input: str
    case_update_allowed: bool
    draft_generated: bool
    resolution_plan: dict[str, Any]
    draft_spec: dict[str, Any]
    draft_content: str
    draft_title: str
    events: Annotated[list[dict[str, Any]], operator.add]
