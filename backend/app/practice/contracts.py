from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StatutorySafeguard(BaseModel):
    section: str
    act: str
    title: str
    relevance: str
    # Set when the safeguard comes from the verified legal index.
    passage_id: str | None = None
    canonical_url: str | None = None
    origin: str | None = None


class CoachFeedback(BaseModel):
    assessment: Literal["strong", "caution", "risky_admission"]
    strengths: list[str] = Field(default_factory=list)
    vulnerabilities: list[str] = Field(default_factory=list)
    statutory_safeguards: list[StatutorySafeguard] = Field(default_factory=list)
    suggested_phrasing: str
    anti_fabrication_warning: str | None = None
    is_crisis: bool = False
    crisis_text: str | None = None


class PracticeScenario(BaseModel):
    scenario_id: str
    title: str
    domain: str
    opponent_role: str
    setting: str
    objective: str
    opening_statement: str
    key_rights: list[str] = Field(default_factory=list)
    suggested_first_response: str | None = None


class PracticeTurn(BaseModel):
    id: str
    session_id: str
    turn_index: int
    user_argument: str
    opponent_reply: str
    coach_feedback: CoachFeedback
    created_at: str


class PracticeSessionCreate(BaseModel):
    scenario_id: str
    title: str | None = None
    opponent_role: str | None = None
    setting: str | None = None
    objective: str | None = None
    opening_statement: str | None = None
    custom_scenario: str | None = None
    language: str = "en"


class PracticeTurnRequest(BaseModel):
    user_argument: str = Field(min_length=1, max_length=4000)
    language: str = "en"


class PracticeSessionResponse(BaseModel):
    id: str
    conversation_id: str
    scenario_id: str
    title: str
    domain: str
    opponent_role: str
    setting: str
    objective: str
    opening_statement: str
    status: str
    created_at: str
    updated_at: str
    turns: list[PracticeTurn] = Field(default_factory=list)


class PracticeExportRequest(BaseModel):
    action_titles: list[str] = Field(default_factory=list)


class RoleplaySetupResponse(BaseModel):
    case_title: str
    case_synopsis: str
    stakeholders: list[str] = Field(default_factory=list)


class RoleplayStartRequest(BaseModel):
    stakeholder: str = Field(max_length=120)
    custom_stakeholder: str | None = Field(default=None, max_length=120)
    language: str = "en"
    # Echoed from /setup so starting a session needs no second extraction call.
    case_title: str | None = Field(default=None, max_length=120)
    case_synopsis: str | None = Field(default=None, max_length=400)


class RoleplayStartResponse(BaseModel):
    session_id: str
    stakeholder: str
    case_title: str
    case_synopsis: str
    opening_message: str


class RoleplayChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    language: str = "en"


class RoleplayReply(BaseModel):
    reply: str
    # False when the reply is safety guidance rather than the character speaking.
    in_character: bool = True
    notice: str | None = None


class RoleplayChatResponse(RoleplayReply):
    turn_index: int
