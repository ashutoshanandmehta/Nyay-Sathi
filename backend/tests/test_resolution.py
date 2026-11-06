"""Domain regression tests and labelled synthetic matrix; never live-model claims."""

import json
from itertools import product
from pathlib import Path

import pytest
from docx import Document
from pydantic import ValidationError

from app.db import Database, MemoryConflict
from app.resolution.documents import CorrespondenceExporter
from app.resolution.drafting import DraftPreparationService
from app.resolution.journey import ComplaintJourneyService, deterministic_journey_updates
from app.resolution.models import ComplaintJourney, JourneyProposal
from app.resolution.planner import (
    ChannelRegistry,
    ConsumerEligibilityPolicy,
    ResolutionPlanner,
    TradeoffEvaluator,
    VersionedFeePolicy,
)
from app.schemas.models import CaseFact, CaseMemory

from .conftest import create_case

MATRIX = json.loads((Path(__file__).parents[2] / "evals/cases/resolution_matrix.json").read_text())


@pytest.mark.parametrize(
    "platform,stage,user_request",
    list(product(MATRIX["platforms"], MATRIX["stages"], MATRIX["requests"])),
    ids=lambda item: item["id"] if isinstance(item, dict) else item,
)
def test_resolution_synthetic_matrix(platform, stage, user_request):
    memory = CaseMemory(domain="consumer", version=1)
    text = stage["message"].format(platform=platform) + " " + user_request
    service = ComplaintJourneyService()
    service.apply(
        memory.journey,
        deterministic_journey_updates(text, platform),
        message_id="synthetic-message",
        evidence=[],
        source_text=text,
        at="2026-11-06T09:00:00+00:00",
    )
    recommendation = ResolutionPlanner().recommend(memory, text)
    assert memory.journey.outcome == stage["outcome"]
    assert recommendation.recommended_route_id == stage["recommended"]
    assert all(route.user_operated for route in recommendation.alternatives)
    assert all(
        route.tradeoff.waiting_time.startswith("Unknown") for route in recommendation.alternatives
    )
    if stage["id"] != "new":
        assert len(memory.journey.submissions) == 1
    if "chat" in user_request or "email" in user_request:
        spec = DraftPreparationService(ChannelRegistry()).prepare(
            memory, recommendation, text, "draft"
        )
        if stage["recommended"]:
            assert spec and spec.channel == ("chat" if "chat" in user_request else "email")
            assert spec.execution_note.startswith("Prepared only")


def test_requested_nch_preparation_does_not_force_another_support_complaint():
    memory = CaseMemory(domain="consumer", version=1)
    recommendation = ResolutionPlanner().recommend(
        memory, "The seller refused my refund. Explain the NCH complaint procedure."
    )
    assert recommendation.recommended_route_id == "nch"
    route = next(r for r in recommendation.alternatives if r.route_id == "nch")
    assert route.eligibility.status == "insufficient_information"


def test_requested_external_route_does_not_override_material_contradictions():
    memory = CaseMemory(
        domain="consumer",
        version=1,
        contradictions=[{"description": "Conflicting transaction dates", "resolved": False}],
    )
    recommendation = ResolutionPlanner().recommend(memory, "Explain NCH filing.")
    assert recommendation.recommended_route_id is None


def test_one_message_projects_events_in_narrative_order():
    journey = ComplaintJourney()
    text = "I contacted Blinkit support. They promised a refund. They closed my ticket."
    ComplaintJourneyService().apply(
        journey,
        deterministic_journey_updates(text, "blinkit"),
        message_id="m",
        evidence=[],
        source_text=text,
    )
    assert journey.outcome == "closed_by_recipient_outcome_unknown"
    assert [e.event_type.value for e in journey.events] == [
        "complaint_submitted",
        "remedy_promised",
        "ticket_closed",
    ]


def test_append_only_correction_and_idempotent_events():
    service = ComplaintJourneyService()
    journey = ComplaintJourney()
    event = JourneyProposal(
        event_type="complaint_submitted", description="Sent to Amazon", recipient="amazon"
    )
    assert service.apply(journey, [event], message_id="m1", evidence=[])
    assert not service.apply(journey, [event], message_id="m1", evidence=[])
    original = journey.events[0]
    with pytest.raises(ValidationError):
        original.description = "overwrite"
    correction = JourneyProposal(
        event_type="complaint_submitted",
        description="Actually sent to Flipkart",
        recipient="flipkart",
        supersedes_id=original.id,
    )
    service.apply(journey, [correction], message_id="m2", evidence=[])
    assert len(journey.events) == 2 and len(journey.submissions) == 1
    assert journey.submissions[0].recipient == "flipkart"


def test_untrusted_document_identity_and_invented_year_are_rejected():
    service = ComplaintJourneyService()
    journey = ComplaintJourney()
    service.apply(
        journey,
        [
            JourneyProposal(
                event_type="response_received",
                description="Reply",
                source_type="document",
                source_id="foreign",
            )
        ],
        message_id="m",
        evidence=[],
    )
    assert not journey.events
    service.apply(
        journey,
        [
            JourneyProposal(
                event_type="complaint_submitted",
                description="Sent 12 October",
                occurred_at="2026-10-12",
            )
        ],
        message_id="m",
        evidence=[],
        source_text="I complained on 12 October",
    )
    assert journey.events[0].occurred_at is None


def test_closed_ticket_and_processed_refund_are_not_received_remedies():
    service = ComplaintJourneyService()
    journey = ComplaintJourney()
    service.apply(
        journey,
        [
            JourneyProposal(event_type="refund_processed", description="They say processed"),
            JourneyProposal(event_type="ticket_closed", description="Ticket closed"),
        ],
        message_id="m",
        evidence=[],
    )
    assert journey.outcome == "closed_by_recipient_outcome_unknown"
    assert journey.satisfaction == "unknown"


def test_promise_clock_is_separate_from_statutory_deadline():
    journey = ComplaintJourney()
    ComplaintJourneyService().apply(
        journey,
        [
            JourneyProposal(
                event_type="remedy_promised",
                description="Refund promised by 2026-11-04",
                promised_by="2026-11-04",
            )
        ],
        message_id="m",
        evidence=[],
        source_text="Refund promised by 2026-11-04",
        at="2026-11-06T09:00:00+00:00",
    )
    assert journey.commitments[0].status == "past_reported_target"
    assert journey.commitments[0].clock_type.endswith("not_statutory_deadline")


@pytest.mark.parametrize(
    "amount,fee,band",
    [
        (500000, "0", "District"),
        (500000.01, "200", "District"),
        (1000000, "200", "District"),
        (1000000.01, "400", "District"),
        (5000000, "1000", "District"),
        (5000000.01, "2000", "State"),
        (20000000, "2500", "State"),
        (20000000.01, "3000", "National"),
    ],
)
def test_fee_and_jurisdiction_boundaries(amount, fee, band):
    result = VersionedFeePolicy().calculate(amount, "2026-11-06")
    assert result["amount"] == fee and result["pecuniary_band"].startswith(band)


def test_fee_never_uses_compensation_or_budget_and_future_rule_inactive():
    memory = CaseMemory(
        facts={
            "requested_compensation": CaseFact(key="requested_compensation", value="8000000"),
            "budget_inr": CaseFact(key="budget_inr", value="200"),
        }
    )
    assert TradeoffEvaluator().estimate(memory, "commission").filing_fee_inr is None
    policy = VersionedFeePolicy()
    assert not policy.active(policy.data["future_provisions"][0], "2026-11-06")
    assert policy.active(policy.data["future_provisions"][0], "2027-01-01")
    assert policy.calculate("NaN")["amount"] is None


def test_upi_merchant_dispute_does_not_create_rbi_route_and_safety_overrides_cost():
    memory = CaseMemory(domain="consumer")
    normal = ResolutionPlanner().recommend(memory, "My Blinkit order was missing. I paid by UPI.")
    assert "rbi" not in [r.recipient_id for r in normal.alternatives]
    safety = ResolutionPlanner().recommend(
        memory, "My Blinkit order contained contaminated food worth ₹50."
    )
    assert safety.recommended_route_id == "food_safety"


def test_formal_eligibility_unknown_without_inputs_and_parallel_route_checks():
    policy = ConsumerEligibilityPolicy()
    memory = CaseMemory(domain="consumer")
    assert policy.evaluate(memory, "commission").status == "insufficient_information"
    ComplaintJourneyService().apply(
        memory.journey,
        [
            JourneyProposal(
                event_type="complaint_submitted", description="Filed", recipient="commission"
            )
        ],
        message_id="m",
        evidence=[],
    )
    assert "parallel" in " ".join(policy.evaluate(memory, "nch").reasons)


def test_journey_and_recommendations_persist_atomically_and_delete(tmp_path):
    db = Database(tmp_path / "case.sqlite3")
    owner = db.create_owner("test")
    cid = db.create_conversation(owner, "en")["id"]
    memory, _ = db.load_memory(owner, cid)
    ComplaintJourneyService().apply(
        memory.journey,
        deterministic_journey_updates("I contacted Amazon support.", "amazon"),
        message_id="m",
        evidence=[],
    )
    memory.version = 1
    memory.journey.recommendations = [ResolutionPlanner().recommend(memory, "Amazon")]
    db.save_memory(cid, memory, "", expected_version=0)
    with pytest.raises(MemoryConflict):
        db.save_memory(cid, memory, "", expected_version=0)
    loaded, _ = Database(db.path).load_memory(owner, cid)
    assert loaded.journey.submissions[0].recipient == "amazon"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM complaint_events").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM resolution_recommendations").fetchone()[0] == 1
    db.delete_conversation(owner, cid)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM complaint_events").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM resolution_recommendations").fetchone()[0] == 0


def test_clean_draft_export_and_conflicting_edits(client):
    cid = create_case(client)
    draft = client.post(
        f"/api/conversations/{cid}/drafts",
        json={
            "title": "Refund request",
            "content": "Dear Support,\nPlease check my refund.\n[Name]",
        },
    ).json()
    patch = {
        "title": "Refund request",
        "content": "Please refund the reported amount.",
        "expected_version": 1,
    }
    assert (
        client.patch(f"/api/conversations/{cid}/drafts/{draft['id']}", json=patch).status_code
        == 200
    )
    assert (
        client.patch(f"/api/conversations/{cid}/drafts/{draft['id']}", json=patch).status_code
        == 409
    )
    response = client.get(f"/api/conversations/{cid}/drafts/{draft['id']}/export/docx")
    assert response.status_code == 200 and response.content.startswith(b"PK")
    assert client.get(f"/api/conversations/{cid}/drafts/foreign/export/docx").status_code == 404


def test_correspondence_export_has_no_case_pack_or_fabricated_identity(tmp_path):
    path = tmp_path / "request.docx"
    CorrespondenceExporter().docx(
        path, "Refund request", "Dear Support,\nPlease check order [Order ID].\n[Name]"
    )
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "[Order ID]" in text and "[Name]" in text
    assert "Case Pack" not in text and "Advocate" not in text
