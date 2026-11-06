"""Models may propose content and review findings; only the engine publishes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.memory.patches import CasePatch, PatchVerdict
from app.schemas.models import DateCalculation, LegalActionClaim, ToolUseClaim

Severity = Literal["critical", "major", "moderate", "minor", "advisory"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionRecommendation(StrictModel):
    action: str = Field(min_length=1, max_length=2000)
    rationale_claim_ids: list[str] = Field(default_factory=list, max_length=16)
    evidence_ids: list[str] = Field(default_factory=list, max_length=32)
    prerequisites: list[str] = Field(default_factory=list, max_length=16)
    limitations: list[str] = Field(default_factory=list, max_length=16)


class CandidateClaim(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    kind: Literal[
        "factual",
        "draft",
        "legal",
        "procedural",
        "safety",
        "general",
        "precaution",
        "recommendation",
        "preparation",
        "external_fact",
        "legal_procedure",
        "legal_conclusion",
        "limitation",
        "question",
    ]
    text: str = Field(max_length=10000)
    evidence_ids: list[str] = Field(max_length=32)
    depends_on: list[str] = Field(max_length=32)
    legal_action: LegalActionClaim | None = None
    date_calculation: DateCalculation | None = None
    tool_claims: list[ToolUseClaim] = Field(default_factory=list, max_length=16)


class CandidateUnit(StrictModel):
    unit_id: str = Field(min_length=1, max_length=80)
    task_id: str
    claims: list[CandidateClaim] = Field(max_length=16)
    action_recommendations: list[ActionRecommendation] = Field(default_factory=list, max_length=8)
    unresolved: list[str] = Field(max_length=6)
    document_title: str | None
    document_claim_ids: list[str]
    document_ready_to_send: bool = False


class CandidateBatch(StrictModel):
    schema_version: Literal["answer-units-v1", "turn-candidates-v2"] = "answer-units-v1"
    units: list[CandidateUnit] = Field(max_length=16)
    case_patches: list[CasePatch] = Field(default_factory=list, max_length=24)


class ReviewFinding(StrictModel):
    code: str
    severity: Severity
    reason: str


class UnresolvedClaimExplanation(StrictModel):
    claim_id: str = Field(min_length=1, max_length=80)
    explanation: str = Field(min_length=1, max_length=500)


class CorrectnessReview(StrictModel):
    unsupported_claims: list[str] = Field(default_factory=list, max_length=32)
    legal_source_failures: list[str] = Field(default_factory=list, max_length=32)
    provenance_failures: list[str] = Field(default_factory=list, max_length=32)


class UsefulnessReview(StrictModel):
    requested_deliverables_complete: bool = True
    primary_question_answered: bool = True
    recommended_action_clear: bool = True
    important_supported_facts_preserved: bool = True
    avoidable_clarification: bool = False
    unnecessary_disclaimer: bool = False
    missing_elements: list[str] = Field(default_factory=list, max_length=12)
    improvement_instructions: list[str] = Field(default_factory=list, max_length=8)


class ClaimReview(StrictModel):
    claim_id: str
    support: Literal["supported", "uncertain", "unsupported"]
    findings: list[ReviewFinding]
    content_type: (
        Literal[
            "factual",
            "practical",
            "external_fact",
            "legal_procedure",
            "legal_conclusion",
            "safety",
            "precaution",
            "other",
        ]
        | None
    ) = None


class TaskReview(StrictModel):
    task_id: str
    completion: Literal["answered", "partial", "deferred", "clarification_required"]
    reason: str
    user_limitation: str | None = Field(default=None, max_length=500)


class UnitReviewBatch(StrictModel):
    schema_version: Literal["review-v1", "review-v2"] = "review-v1"
    claims: list[ClaimReview]
    task_reviews: list[TaskReview] = Field(default_factory=list)
    findings: list[ReviewFinding]
    case_updates_supported: bool
    case_update_reason: str
    patch_verdicts: list[PatchVerdict] = Field(default_factory=list, max_length=24)
    correctness_review: CorrectnessReview = Field(default_factory=CorrectnessReview)
    usefulness_review: UsefulnessReview = Field(default_factory=UsefulnessReview)
    unresolved_claims: list[UnresolvedClaimExplanation] = Field(default_factory=list, max_length=16)


class VerifiedClaim(StrictModel):
    claim_id: str
    kind: str
    text: str
    evidence_ids: list[str]


class VerifiedUnit(StrictModel):
    unit_id: str
    task_id: str
    status: Literal["supported", "partial", "deferred", "blocked"]
    claims: list[VerifiedClaim]
    action_recommendations: list[ActionRecommendation] = Field(default_factory=list)
    unresolved: list[str]
    unresolved_explanations: list[str] = Field(default_factory=list)
    findings: list[ReviewFinding]
    document_title: str | None
    document: str | None
    assistance_status: str = "deferred"
    document_status: str = "not_applicable"
    legal_verification_status: str = "not_required"


class ResponseQualityScorecard(StrictModel):
    requested_task_completion: float = Field(ge=0.0, le=5.0)
    factual_and_legal_accuracy: float = Field(ge=0.0, le=5.0)
    actionability_and_next_steps: float = Field(ge=0.0, le=5.0)
    document_usefulness: float = Field(ge=0.0, le=5.0)
    clarity_and_concision: float = Field(ge=0.0, le=5.0)
    serious_safety_failure: bool = False
    safety_failure_reasons: list[str] = Field(default_factory=list, max_length=16)

    @property
    def weighted_score_100(self) -> float:
        return round(
            (
                self.requested_task_completion * 0.25
                + self.factual_and_legal_accuracy * 0.30
                + self.actionability_and_next_steps * 0.20
                + self.document_usefulness * 0.15
                + self.clarity_and_concision * 0.10
            )
            * 20.0,
            2,
        )

    @property
    def passes_safety_and_quality(self) -> bool:
        return not self.serious_safety_failure and self.factual_and_legal_accuracy >= 4
