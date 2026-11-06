from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.resolution.models import ComplaintJourney, DraftSpecification, JourneyProposal


class Language(StrEnum):
    ENGLISH = "en"
    HINDI = "hi"
    HINGLISH = "hinglish"


class FactStatus(StrEnum):
    ALLEGED = "user_allegation"
    DOCUMENT = "document_statement"
    CONFIRMED = "user_confirmed"
    INFERENCE = "assistant_inference"
    UNKNOWN = "unknown"


class Provenance(BaseModel):
    source_type: Literal["message", "document", "assistant"]
    source_id: str
    page: int | None = None
    span: str | None = None


class CaseFact(BaseModel):
    key: str
    value: str
    status: FactStatus = FactStatus.ALLEGED
    provenance: list[Provenance] = Field(default_factory=list)
    previous_values: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CaseMemory(BaseModel):
    version: int = 0
    domain: str = "unknown"
    parties: list[dict[str, Any]] = Field(default_factory=list)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    facts: dict[str, CaseFact] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    requested_remedy: str | None = None
    requested_remedy_provenance: list[Provenance] = Field(default_factory=list)
    actions_completed: list[str] = Field(default_factory=list)
    action_provenance: dict[str, list[Provenance]] = Field(default_factory=dict)
    responses_received: list[dict[str, Any]] = Field(default_factory=list)
    correspondence_history: list[dict[str, Any]] = Field(default_factory=list)
    questions_for_legal_review: list[str] = Field(default_factory=list)
    legal_issues_for_review: list[str] = Field(default_factory=list)
    urgent_matters: list[dict[str, Any]] = Field(default_factory=list)
    options_discussed: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    stale_draft_ids: list[str] = Field(default_factory=list)
    pending_questions: list[dict[str, Any]] = Field(default_factory=list)
    last_proposed_fact_keys: list[str] = Field(default_factory=list)
    journey: ComplaintJourney = Field(default_factory=ComplaintJourney)
    last_draft_spec: DraftSpecification | None = None


class ConversationCreate(BaseModel):
    language: Language = Language.ENGLISH


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=8, max_length=100)
    language: Language | None = None
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationOut(BaseModel):
    id: str
    title: str
    language: str
    created_at: str
    updated_at: str
    last_message: str | None = None


class TurnResponse(BaseModel):
    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut
    case_version: int
    sources: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    token_usage: dict[str, int] = Field(default_factory=dict)
    ai_configured: bool


class ProposedFact(BaseModel):
    key: str
    value: str
    status: FactStatus

    def __getitem__(self, key: str) -> str:
        return getattr(self, key)

    def get(self, key: str, default: str | None = None) -> str | None:
        return getattr(self, key, default)


class IntakeParty(BaseModel):
    name: str
    role: str


class IntakeLocation(BaseModel):
    value: str
    role: str


class IntakeEvent(BaseModel):
    date: str | None
    description: str


class IntakeResponseReceived(BaseModel):
    from_party: str
    date: str | None
    content: str


class IntakeCorrespondence(BaseModel):
    direction: Literal["sent", "received", "unknown"]
    party: str
    date: str | None
    description: str


class ExplicitRequest(BaseModel):
    request_id: str
    kind: Literal[
        "evidence_checklist",
        "factual_summary",
        "draft",
        "revision",
        "translation",
        "options",
        "practice",
        "explanation",
        "case_update",
        "other",
    ]
    request_text: str
    requires_legal_retrieval: bool


class IntakeExtraction(BaseModel):
    domain: Literal[
        "consumer",
        "landlord_deposit",
        "unpaid_salary",
        "employment",
        "criminal",
        "other_unsupported",
        "unknown",
    ]
    proposed_facts: list[ProposedFact]
    parties: list[IntakeParty]
    locations: list[IntakeLocation]
    events: list[IntakeEvent]
    requested_remedy: str | None
    completed_actions: list[str]
    responses_received: list[IntakeResponseReceived]
    correspondence: list[IntakeCorrespondence]
    contradictions: list[str]
    urgent_reason: str | None
    needs_legal_retrieval: bool
    intent: Literal["intake", "options", "draft", "practice", "conversation"]
    questions: list[str] = Field(max_length=2)
    explicit_requests: list[ExplicitRequest]
    journey_updates: list[JourneyProposal] = Field(default_factory=list)


class RequestCoverageItem(BaseModel):
    request_id: str
    status: Literal["answered", "deferred", "clarification_required"]
    reason: str | None


class LegalActionClaim(BaseModel):
    route_id: str
    status: Literal["research_candidate", "preparation_only", "eligible_destination"]
    passage_ids: list[str]
    jurisdiction: str | None
    effective_date: str | None
    limitations: str


class ToolUseClaim(BaseModel):
    task_id: str
    tool: Literal["web_search", "source_fetch", "legal_corpus"]
    status: str


class DateCalculation(BaseModel):
    kind: Literal["calendar_arithmetic", "reported_company_target", "statutory_deadline"]
    start_date: str
    days: int = Field(ge=-36500, le=36500)
    result_date: str
    rule_id: str | None


class ResponseEnvelope(BaseModel):
    message_markdown: str
    request_coverage: list[RequestCoverageItem]
    follow_up_questions: list[str] = Field(max_length=2)
    document_markdown: str | None = None
    document_title: str | None = None
    legal_recommendations: list[LegalActionClaim] = Field(default_factory=list)
    tool_claims: list[ToolUseClaim] = Field(default_factory=list)
    date_calculations: list[DateCalculation] = Field(default_factory=list)
    document_ready_to_send: bool = False


class VerificationFinding(BaseModel):
    code: str
    reason: str


class ResponseReview(BaseModel):
    passed: bool
    factual_support_passed: bool
    legal_support_passed: bool
    tone_safe: bool
    request_coverage_passed: bool
    confirmation_handling_passed: bool
    findings: list[VerificationFinding]
    revision_instructions: list[str]


class VerificationResult(BaseModel):
    passed: bool
    factual_support_passed: bool
    legal_support_passed: bool
    tone_safe: bool
    findings: list[VerificationFinding]
    unsupported_claims: list[str]
    revision_required: bool
