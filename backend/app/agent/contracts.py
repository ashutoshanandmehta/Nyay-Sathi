"""Internal contracts. Models propose meaning; runtime controls tools and publication."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.memory.patches import CasePatch, PatchVerdict

BlockType = Literal[
    "direct_answer",
    "immediate_actions",
    "recommended_route",
    "alternatives",
    "evidence_checklist",
    "document",
    "question",
    "limitation",
    "human_handoff",
]

GroundingLabel = Literal[
    "reported_by_user",
    "practical_precaution",
    "verified_legal_source",
    "requires_confirmation",
]

RiskType = Literal[
    "physical_danger",
    "financial_fraud",
    "digital_compromise",
    "medical_danger",
    "deadline_risk",
    "domestic_violence",
    "self_harm",
    "legal_uncertainty",
]

SafetyCategory = Literal[
    "physical_safety",
    "financial_cyber_fraud",
    "domestic_violence",
    "self_harm",
    "medical_emergency",
]

DisputeStage = Literal[
    "intake",
    "active_emergency",
    "internal_support_attempted",
    "internal_grievance_exhausted",
    "regulator_or_prelitigation",
    "forum_or_litigation",
    "follow_up",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlannedAction(Contract):
    action: str = Field(min_length=2, max_length=240)
    channel: str | None = Field(default=None, max_length=120)
    priority: int = Field(default=1, ge=1, le=5)
    time_sensitive: bool = False


class ActionPlan(Contract):
    user_intent: str = Field(min_length=2, max_length=120)
    primary_goal: str = Field(min_length=4, max_length=400)
    jurisdiction: str = Field(default="India", max_length=80)
    urgency: Literal["ordinary", "high", "critical"] = "ordinary"
    risk_types: list[RiskType] = Field(default_factory=list, max_length=6)
    dispute_stage: DisputeStage = "intake"
    actions_already_taken: list[str] = Field(default_factory=list, max_length=12)
    exhausted_channels: list[str] = Field(default_factory=list, max_length=8)
    next_actions: list[PlannedAction] = Field(default_factory=list, max_length=6)
    research_needs: list[str] = Field(default_factory=list, max_length=6)
    required_answer_elements: list[BlockType] = Field(default_factory=list, max_length=8)
    plan_revised_after_research: bool = False


class ResearchQuestion(Contract):
    query: str = Field(min_length=8, max_length=500)
    jurisdiction: str | None = None
    material_gap: str = Field(min_length=4, max_length=500)


class ResearchRequest(Contract):
    questions: list[ResearchQuestion] = Field(min_length=1, max_length=2)
    fresh_required: bool = False


class AgentTask(Contract):
    task_id: str = Field(pattern=r"^task-[1-8]$")
    title: str = Field(min_length=1, max_length=120)
    intent: Literal[
        "information",
        "legal_options",
        "draft",
        "revision",
        "summary",
        "evidence",
        "practice",
        "conversation",
        "case_update",
    ]
    domain: str = Field(min_length=1, max_length=80)
    case_link: Literal["new", "existing", "unrelated", "uncertain"]
    relationship: str | None = None
    source_segment_ids: list[str] = Field(default_factory=list, max_length=32)


class AnswerClaim(Contract):
    claim_id: str = Field(min_length=1, max_length=80)
    task_id: str
    kind: Literal[
        "factual",
        "practical",
        "legal",
        "procedure",
        "safety",
        "question",
        "limitation",
        "document",
        "quote",
        "template",
    ]
    text: str = Field(max_length=10000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=24)
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    template_id: str | None = None
    in_document: bool = False
    block_type: BlockType | None = None
    grounding: GroundingLabel | None = None
    optional: bool = False


class AgentAnswer(Contract):
    central_question: str = Field(min_length=1, max_length=600)
    tasks: list[AgentTask] = Field(min_length=1, max_length=8)
    claims: list[AnswerClaim] = Field(max_length=48)
    unresolved: list[str] = Field(default_factory=list, max_length=8)
    risk: Literal["ordinary", "sensitive", "urgent"] = "ordinary"
    risk_types: list[RiskType] = Field(default_factory=list, max_length=6)
    action_plan: ActionPlan | None = None
    case_patches: list[CasePatch] = Field(default_factory=list, max_length=24)
    factual_issues: list[str] = Field(default_factory=list, max_length=8)
    legal_issues: list[str] = Field(default_factory=list, max_length=8)
    case_stage: str | None = None
    next_action: str | None = None

    @model_validator(mode="after")
    def identities(self):
        tasks = {t.task_id for t in self.tasks}
        claims = {c.claim_id for c in self.claims}
        if len(tasks) != len(self.tasks) or len(claims) != len(self.claims):
            raise ValueError("Duplicate task or claim identity")
        if any(c.task_id not in tasks for c in self.claims):
            raise ValueError("Claim references an unknown task")
        if any(p.task_id not in tasks for p in self.case_patches):
            raise ValueError("Patch references an unknown task")
        return self


class ClaimVerdict(Contract):
    claim_id: str
    support: Literal["supported", "uncertain", "unsupported"]
    reason: str = Field(max_length=800)
    requires_public_evidence: bool = True


class AgentReview(Contract):
    claims: list[ClaimVerdict] = Field(max_length=48)
    patch_verdicts: list[PatchVerdict] = Field(default_factory=list, max_length=24)
    primary_question_answered: bool
    next_action_useful: bool
    cross_block_coherent: bool = True
    exhausted_channel_respected: bool = True
    pinpoint_citations_verified: bool = True
    repair_instructions: list[str] = Field(default_factory=list, max_length=8)


class BlockSourceRef(Contract):
    source_id: str
    title: str
    locator: str
    canonical_url: str


class ResolutionBlock(Contract):
    """Output-only structured block rendered by the copilot UI."""

    block_id: str
    block_type: BlockType
    title: str
    content: str
    items: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    sources: list[BlockSourceRef] = Field(default_factory=list)
    grounding: GroundingLabel
    document_title: str | None = None
