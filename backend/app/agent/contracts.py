"""Internal contracts. Models propose meaning; runtime controls tools and publication."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.memory.patches import CasePatch, PatchVerdict


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class AgentAnswer(Contract):
    central_question: str = Field(min_length=1, max_length=600)
    tasks: list[AgentTask] = Field(min_length=1, max_length=8)
    claims: list[AnswerClaim] = Field(max_length=48)
    unresolved: list[str] = Field(default_factory=list, max_length=8)
    risk: Literal["ordinary", "sensitive", "urgent"] = "ordinary"
    case_patches: list[CasePatch] = Field(default_factory=list, max_length=24)

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
    repair_instructions: list[str] = Field(default_factory=list, max_length=8)
