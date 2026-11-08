"""Lawyer escalation bundle: specific reasons, and open points kept apart by kind."""

from app.escalation.bundle import build_escalation_bundle
from app.schemas.models import CaseMemory

USER_QUESTION = (
    "I can't tell from your message what charges were recorded. If you can share the FIR "
    "sections and the name of the court, I can help explain the next step."
)
LIMITATION = "Current Bihar prohibition-law charges are not confirmed because the FIR is unavailable [1](#cite-1)."


def _bundle(memory, *, safety=()):
    message = {
        "id": "a1",
        "role": "assistant",
        "status": "complete",
        "metadata": {
            "legal_issues": ["Whether bail is available for the offence recorded in the FIR"],
            "factual_issues": ["Which police station registered the FIR"],
            "resolution_blocks": [
                {"block_type": "question", "content": USER_QUESTION},
                {"block_type": "limitation", "content": LIMITATION},
            ],
            "sources": [
                {"source_id": "s", "passage_id": "p", "title": "BNSS", "locator": "Section 480"}
            ],
        },
    }
    return build_escalation_bundle(
        conversation={"id": "c1", "title": "Liquor case", "language": "en"},
        memory=memory,
        summary="",
        messages=[message],
        attachments=[],
        drafts=[],
        safety_messages=list(safety),
        user_actions=[],
        submission_steps=[],
    )


def test_open_points_are_split_and_exclude_questions_to_the_user():
    bundle = _bundle(CaseMemory(domain="criminal", unknowns=["Date of arrest"]))
    assert bundle["questions_for_counsel"] == [
        "Whether bail is available for the offence recorded in the FIR"
    ]
    assert bundle["facts_to_establish"] == [
        "Date of arrest",
        "Which police station registered the FIR",
    ]
    assert bundle["not_confirmed"] == [
        "Current Bihar prohibition-law charges are not confirmed because the FIR is unavailable."
    ]
    assert USER_QUESTION not in str(bundle)
    assert bundle["executive_summary"] == ""


def test_reasons_name_what_actually_happened():
    criminal = _bundle(CaseMemory(domain="criminal"))
    assert criminal["escalation_reasons"][0].startswith("Criminal matter: personal liberty")
    assert not any("Safety guidance" in r for r in criminal["escalation_reasons"])

    consumer = _bundle(
        CaseMemory(domain="consumer", urgent_matters=[{"reason": "Hearing on Monday"}]),
        safety=[{"type": "safety"}],
    )
    assert consumer["escalation_reasons"][:2] == [
        "Safety guidance was shown during this conversation.",
        "Urgent: Hearing on Monday",
    ]
