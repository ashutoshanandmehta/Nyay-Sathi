from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EntityMention(Contract):
    name: str = Field(max_length=160)
    kind: Literal["organization", "person", "authority", "other"]
    role: str = Field(max_length=160)
    identity_status: Literal["mentioned", "ambiguous"]


class TaskIntent(Contract):
    task_id: str = Field(pattern=r"^task-[1-8]$")
    source_text: str = Field(min_length=1, max_length=12000)
    intent: Literal[
        "information",
        "search",
        "legal_options",
        "evidence",
        "draft",
        "revision",
        "summary",
        "practice",
        "case_update",
        "confirmation",
        "conversation",
        "clarify",
    ]
    domain: Literal[
        "consumer",
        "employment",
        "tenancy",
        "criminal",
        "general",
        "health",
        "animal_health",
        "other_legal",
        "unknown",
    ]
    relationship: str | None = Field(max_length=200)
    entities: list[EntityMention] = Field(max_length=12)
    case_link: Literal["existing", "new", "unrelated", "uncertain"]
    requires_research: bool
    requires_case_update: (
        bool  # Proposal only; policy grants no authority based on this flag alone.
    )
    risk_level: Literal["ordinary", "sensitive", "urgent"]
    uncertainty: list[str] = Field(max_length=8)
    public_query: str | None = Field(max_length=500)
    source_segment_ids: list[str] = Field(default_factory=list)
    needs_early_extraction: bool = False
    extraction_reason: str | None = None


class RequestInterpretation(Contract):
    schema_version: Literal["request-v1", "request-v2"] = "request-v1"
    tasks: list[TaskIntent] = Field(min_length=1, max_length=8)
    case_relevance: Literal["existing", "new", "unrelated", "mixed", "uncertain"]
    clarification_needed: bool
    requested_deliverables: list[str] = Field(default_factory=list, max_length=8)
    user_goal: str | None = Field(default=None, max_length=200)
    suggested_remedy: str | None = Field(default=None, max_length=200)
    required_answer_elements: list[str] = Field(default_factory=list, max_length=12)
    missing_details: list[str] = Field(default_factory=list, max_length=12)
    invalid_tasks: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({t.task_id for t in self.tasks}) != len(self.tasks):
            raise ValueError("Task IDs must be unique")
        return self


class TaskExecution(Contract):
    task_id: str
    workflow: Literal["consumer", "legal_handoff", "general", "safety", "clarify", "conversation"]
    status: Literal["ready", "researched", "deferred", "clarification_required"]
    research_status: str
    reason: str


class CaseUpdateProposal(Contract):
    schema_version: Literal["case-update-v1"] = "case-update-v1"
    base_version: int
    source_message_id: str
    source_task_ids: list[str]
    proposed_memory: dict
    summary: str
