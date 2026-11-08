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


# ---- formal third-person wording, de-duplication, formal rewrite and downloads ------------

import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from app.config import Settings  # noqa: E402
from app.escalation import brief as brief_module  # noqa: E402
from app.escalation.bundle import formal_text  # noqa: E402
from app.resolution.models import ComplaintEvent, ComplaintJourney  # noqa: E402

EVENT = "User reports that police stopped the brother's car and took him to jail."


def _custody_memory():
    journey = ComplaintJourney(
        events=[
            ComplaintEvent(
                id="e1",
                event_type="incident",
                description=EVENT,
                recorded_at="2026-11-08T10:00:00Z",
                source_id="m1",
                evidence_status="user_reported",
            )
        ]
    )
    return CaseMemory(
        domain="other_legal",
        journey=journey,
        events=[{"date": None, "description": EVENT + "."}],
        facts={},
    )


def test_wording_is_third_person_for_a_lawyer():
    assert formal_text(EVENT) == "Police stopped the brother's car and took him to jail."
    assert formal_text("Whether the user's father owns the car") == (
        "Whether the client's father owns the car"
    )


def test_repeated_event_is_kept_once_with_its_date_and_liberty_is_detected():
    bundle = _bundle(_custody_memory())
    assert [(e["date"], e["summary"]) for e in bundle["chronology"]] == [
        ("2026-11-08", "Police stopped the brother's car and took him to jail.")
    ]
    assert bundle["escalation_reasons"][0].startswith("Criminal matter")
    assert "User reports" not in json.dumps(bundle)
    assert bundle["writing"] == "plain"


class FakeResponses:
    def __init__(self, brief):
        self.brief, self.calls = brief, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status="completed", output_text=json.dumps(self.brief))


def _factory(responses):
    class Client:
        def __init__(self, **_):
            self.responses = responses

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return Client


FORMAL = {
    "summary": "According to the client, the police stopped the client's brother and took him into custody.",
    "chronology": [
        {"date": "2026-11-08", "event": "The police stopped the client's brother's car."}
    ],
    "stated_facts": ["The client's brother is in custody."],
    "questions_for_counsel": ["Is bail available for the offence recorded in the FIR?"],
    "facts_to_establish": ["Which police station registered the FIR"],
    "not_confirmed": ["The charges recorded in the FIR."],
}


def test_formal_rewrite_replaces_the_wording_with_one_call():
    responses = FakeResponses(FORMAL)
    bundle, calls = brief_module.formalize(
        _bundle(_custody_memory()),
        Settings(openai_api_key="fixture-not-real"),
        client_factory=_factory(responses),
    )
    assert calls == 1 and bundle["writing"] == "formal"
    assert bundle["executive_summary"].startswith("According to the client")
    assert bundle["chronology"][0]["date"] == "2026-11-08"
    assert bundle["questions_for_counsel"] == FORMAL["questions_for_counsel"]
    sent = responses.calls[0]
    assert sent["text"]["format"]["name"] == "FormalBrief" and sent["store"] is False


def test_formal_rewrite_that_adds_a_number_is_rejected():
    invented = {**FORMAL, "questions_for_counsel": ["Does Section 37 of the Act bar bail?"]}
    original = _bundle(_custody_memory())
    bundle, calls = brief_module.formalize(
        original,
        Settings(openai_api_key="fixture-not-real"),
        client_factory=_factory(FakeResponses(invented)),
    )
    assert calls == 1 and bundle is original and bundle["writing"] == "plain"


def test_offline_bundle_makes_no_call():
    original = _bundle(_custody_memory())
    assert brief_module.formalize(original, Settings(openai_api_key=None)) == (original, 0)


@pytest.mark.parametrize(("fmt", "magic"), [("pdf", b"%PDF"), ("docx", b"PK")])
def test_lawyer_bundle_downloads(client, fmt, magic):
    from tests.conftest import create_case

    cid = create_case(client)
    response = client.get(f"/api/conversations/{cid}/escalation-bundle/export/{fmt}")
    assert response.status_code == 200 and response.content.startswith(magic)
    assert f'filename="nyay-saathi-lawyer-bundle.{fmt}"' in response.headers["content-disposition"]


def test_bundle_is_formalized_once_per_case_state(client, isolated_app, monkeypatch):
    from app.api import routes
    from tests.conftest import create_case

    calls = []

    def fake_formalize(bundle, settings):
        calls.append(1)
        return {**bundle, "writing": "formal"}, 1

    monkeypatch.setattr(routes, "formalize", fake_formalize)
    isolated_app.state.settings = isolated_app.state.settings.model_copy(
        update={"openai_api_key": "fixture-not-real"}
    )
    cid = create_case(client)
    first = client.get(f"/api/conversations/{cid}/escalation-bundle").json()
    client.get(f"/api/conversations/{cid}/escalation-bundle/export/pdf")
    assert first["writing"] == "formal" and len(calls) == 1
