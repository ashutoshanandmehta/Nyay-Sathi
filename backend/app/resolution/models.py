from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    INCIDENT = "incident"
    SUBMITTED = "complaint_submitted"
    ACKNOWLEDGED = "acknowledged"
    RESPONSE = "response_received"
    PROMISED = "remedy_promised"
    PROCESSED = "refund_processed"
    CREDITED = "remedy_received"
    REJECTED = "remedy_rejected"
    CLOSED = "ticket_closed"
    PARTIAL = "partial_remedy"
    SETTLED = "settlement_accepted"
    STOPPED = "pursuit_stopped"
    CORRECTION = "correction"


class JourneyProposal(BaseModel):
    event_type: EventType
    description: str = Field(max_length=1500)
    recipient: str | None = None
    channel: Literal["chat", "email", "form", "phone", "physical", "unknown"] = "unknown"
    occurred_at: str | None = None
    relative_time: str | None = None
    reference: str | None = None
    promised_by: str | None = None
    supersedes_id: str | None = None
    source_type: Literal["message", "document"] = "message"
    source_id: str | None = None
    page: int | None = None


class ComplaintEvent(JourneyProposal):
    model_config = ConfigDict(frozen=True)
    id: str
    recorded_at: str
    source_id: str
    evidence_status: Literal["user_reported", "documentary_statement"]


class Submission(BaseModel):
    id: str
    recipient: str
    channel: str
    submitted_at: str | None
    reference: str | None
    event_id: str
    status: str = "user_reported_submission"


class Commitment(BaseModel):
    event_id: str
    recipient: str | None
    description: str
    due_at: str | None
    status: Literal["pending", "date_unknown", "past_reported_target", "remedy_reported_received"]
    clock_type: str = "reported_company_commitment_not_statutory_deadline"


class EligibilityResult(BaseModel):
    status: Literal["eligible", "ineligible", "insufficient_information"]
    reasons: list[str]
    missing_inputs: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    scope: Literal["preparation", "filing"] = "preparation"
    filing_verified: bool = False


class CostEstimate(BaseModel):
    filing_fee_inr: str | None = None
    fee_basis: str = "Not verified for this route"
    effort: Literal["low", "medium", "high", "unknown"]
    effort_basis: str = "Application preparation estimate, not measured resolution time"
    waiting_time: str = "Unknown; no resolution time promised"
    other_costs: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class RouteOption(BaseModel):
    route_id: str
    recipient_id: str
    title: str
    channel: str
    eligibility: EligibilityResult
    reason: str
    preparation: list[str]
    instructions: list[str]
    source_urls: list[str]
    tradeoff: CostEstimate
    priority: int
    user_operated: bool = True


class Recommendation(BaseModel):
    id: str
    case_version: int
    policy_version: str
    assessed_at: str
    status: str = "proposed_not_submitted"
    recommended_route_id: str | None
    alternatives: list[RouteOption]
    important_uncertainties: list[str]
    stale: bool = False


class ResolutionPreferences(BaseModel):
    budget_inr: str | None = None
    effort_preference: Literal["low", "balanced", "formal", "unknown"] = "unknown"
    acceptable_alternatives: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ComplaintJourney(BaseModel):
    events: list[ComplaintEvent] = Field(default_factory=list)
    submissions: list[Submission] = Field(default_factory=list)
    responses: list[dict] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    outcome: str = "unknown"
    satisfaction: Literal["accepted", "dissatisfied", "unknown"] = "unknown"
    satisfaction_sources: list[str] = Field(default_factory=list)
    severity: Literal["ordinary", "urgent", "safety"] = "ordinary"
    preferences: ResolutionPreferences = Field(default_factory=ResolutionPreferences)
    recommendations: list[Recommendation] = Field(default_factory=list)


class DraftSpecification(BaseModel):
    recipient_id: str
    route_id: str
    channel: str
    purpose: str
    case_version: int
    required_fields: list[str]
    known_details: dict[str, str]
    missing_details: list[str]
    evidence_names: list[str]
    presentation: str
    provenance_note: str = (
        "Use attributed user-reported/documentary facts; do not imply independent verification."
    )
    execution_note: str = "Prepared only; not sent, filed, signed, sworn or notarised."


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
