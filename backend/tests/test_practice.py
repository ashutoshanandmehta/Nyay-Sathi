"""Unit tests for Nyay Saathi Practice Section (Engine, Safety Interceptors, Database)."""

from __future__ import annotations

import pytest

from app.agent.safety import safety_event
from app.db import Database
from app.practice.contracts import PracticeScenario
from app.practice.engine import PracticeEngine
from app.schemas.models import CaseFact, CaseMemory
from app.security.privacy import EnvelopeCipher


def test_scenario_generation_bihar_liquor_case():
    engine = PracticeEngine()
    memory = CaseMemory(
        version=1,
        domain="criminal",
        facts={
            "issue": CaseFact(
                key="issue",
                value="brother arrested with car carrying liquor in bihar",
                status="user_allegation",
            ),
            "location": CaseFact(
                key="location", value="patna to biharsharif", status="user_allegation"
            ),
        },
        actions_completed=[],
        contradictions=[],
        unknowns=[],
        evidence=[],
    )
    scenarios = engine.generate_scenarios(memory, title="My brother was taking his car")
    assert len(scenarios) >= 1
    bihar_scenarios = [s for s in scenarios if s.scenario_id == "bihar-police-interrogation"]
    assert len(bihar_scenarios) == 1
    s = bihar_scenarios[0]
    assert "prohibition" in s.opening_statement.lower()
    # Rights come from the verified index, not from memory.
    assert "Section 38: Right of arrested person to meet an advocate" in " ".join(s.key_rights)
    assert s.opponent_role == "Station House Officer"


def test_scenario_generation_consumer_case():
    engine = PracticeEngine()
    memory = CaseMemory(
        version=1,
        domain="consumer",
        facts={
            "product": CaseFact(
                key="product",
                value="defective phone bought on amazon refund rejected",
                status="user_allegation",
            ),
        },
        actions_completed=[],
        contradictions=[],
        unknowns=[],
        evidence=[],
    )
    scenarios = engine.generate_scenarios(memory, title="Amazon refund refused")
    scenario_ids = [s.scenario_id for s in scenarios]
    assert "consumer-support-escalation" in scenario_ids
    assert "consumer-mediation-commission" in scenario_ids


def test_crisis_interceptor_halts_practice_drill():
    engine = PracticeEngine()
    scenario = PracticeScenario(
        scenario_id="criminal-test",
        title="Test Police Questioning",
        domain="criminal",
        opponent_role="Investigating Officer",
        setting="Police Station",
        objective="Remain calm",
        opening_statement="Answer the questions.",
    )
    user_argument = (
        "They are beating him right now in the station and I want to kill myself please help"
    )
    opponent_reply, feedback = engine.evaluate_and_respond(scenario, [], user_argument)

    assert feedback.is_crisis is True
    # Same approved text as the main chat, so expired helpline numbers are never shown.
    assert feedback.crisis_text == safety_event("en", india=True, category="self_harm")["text"]
    assert "Halted" in opponent_reply


def test_anti_coaching_fabrication_warning():
    engine = PracticeEngine()
    scenario = PracticeScenario(
        scenario_id="criminal-test",
        title="Test Police Questioning",
        domain="criminal",
        opponent_role="Investigating Officer",
        setting="Police Station",
        objective="Remain calm",
        opening_statement="Answer the questions.",
    )
    user_argument = (
        "Can I just create a fake receipt and lie to police that I was never in the car?"
    )
    _, feedback = engine.evaluate_and_respond(scenario, [], user_argument)

    assert feedback.anti_fabrication_warning is not None
    assert "criminal offence" in feedback.anti_fabrication_warning.lower()


def test_criminal_trap_warning_on_inadvertent_ownership_admission():
    engine = PracticeEngine()
    scenario = PracticeScenario(
        scenario_id="bihar-police-interrogation",
        title="Police Questioning",
        domain="criminal",
        opponent_role="Investigating Officer",
        setting="Police Station",
        objective="Remain calm",
        opening_statement="Why should we not book you?",
    )
    # User admits ownership carelessly
    user_argument = "It is my car and I brought it from Patna, but you cannot arrest me!"
    _, feedback = engine.evaluate_and_respond(scenario, [], user_argument)

    assert feedback.assessment == "risky_admission"
    assert any("Trap Warning" in v for v in feedback.vulnerabilities)
    assert any(
        s.passage_id == "pack-bnss-2023-s38" and s.section.startswith("Section 38")
        for s in feedback.statutory_safeguards
    )


def test_consumer_strengths_and_safeguards():
    engine = PracticeEngine()
    scenario = PracticeScenario(
        scenario_id="consumer-support-escalation",
        title="Support Call",
        domain="consumer",
        opponent_role="Grievance Officer",
        setting="Support Phone",
        objective="Seek refund",
        opening_statement="We cannot issue any refund.",
    )
    user_argument = "I have proof from our security guard that no courier arrived. I am filing a grievance with NCH 1915 under Consumer Protection Rules 2020."
    _, feedback = engine.evaluate_and_respond(scenario, [], user_argument)

    assert feedback.assessment == "strong"
    assert any("NCH" in s for s in feedback.strengths)
    assert any(
        s.passage_id == "prop-consumer-ecommerce-grievance-r4"
        for s in feedback.statutory_safeguards
    )


def test_database_practice_session_and_turns(tmp_path):
    db = Database(tmp_path / "test.db", cipher=EnvelopeCipher("0" * 32, "test-key"), encrypt=True)
    with db.connect() as c:
        c.execute("INSERT INTO owners VALUES ('owner-1', 'token-1', '2026-11-08T00:00:00Z')")
        c.execute(
            "INSERT INTO conversations VALUES ('c1', 'owner-1', 'Car Case', 'en', '2026-11-08T00:00:00Z', '2026-11-08T00:00:00Z', NULL)"
        )

    # 1. Create session
    session = db.create_practice_session(
        owner_id="owner-1",
        cid="c1",
        scenario_id="bihar-police-interrogation",
        title="Police Interrogation",
        domain="criminal",
        opponent_role="Investigating Officer",
        setting="Thana",
        objective="Assert BNSS 38",
        opening_statement="Why were you carrying alcohol?",
    )
    assert session["id"] is not None
    assert session["status"] == "active"

    # 2. Add turn
    coach_data = {
        "assessment": "strong",
        "strengths": ["Calm delivery"],
        "vulnerabilities": [],
        "statutory_safeguards": [
            {"section": "38", "act": "BNSS", "title": "Lawyer", "relevance": "Meet lawyer"}
        ],
        "suggested_phrasing": "I want to speak to my advocate.",
    }
    turn = db.add_practice_turn(
        owner_id="owner-1",
        cid="c1",
        session_id=session["id"],
        user_argument="I was only a passenger and have right to an advocate under BNSS 38.",
        opponent_reply="The driver says you ordered the trip.",
        coach_feedback=coach_data,
    )
    assert turn["turn_index"] == 1
    assert (
        turn["user_argument"]
        == "I was only a passenger and have right to an advocate under BNSS 38."
    )

    # 3. Retrieve session with decrypted turns
    retrieved = db.get_practice_session("owner-1", "c1", session["id"])
    assert len(retrieved["turns"]) == 1
    assert (
        retrieved["turns"][0]["user_argument"]
        == "I was only a passenger and have right to an advocate under BNSS 38."
    )
    assert retrieved["turns"][0]["opponent_reply"] == "The driver says you ordered the trip."
    assert retrieved["turns"][0]["coach_feedback"]["assessment"] == "strong"

    # 4. List sessions
    sessions_list = db.list_practice_sessions("owner-1", "c1")
    assert len(sessions_list) == 1
    assert sessions_list[0]["turn_count"] == 1

    # 5. Update session status
    updated = db.update_practice_session_status("owner-1", "c1", session["id"], "completed")
    assert updated["status"] == "completed"


def test_practice_api_full_flow(client):
    from tests.conftest import create_case

    cid = create_case(client)

    # 1. Scenarios endpoint
    sc_res = client.get(f"/api/conversations/{cid}/practice/scenarios")
    assert sc_res.status_code == 200
    scenarios = sc_res.json()
    assert len(scenarios) >= 1
    sc_id = scenarios[0]["scenario_id"]

    # 2. Start session endpoint
    start_res = client.post(
        f"/api/conversations/{cid}/practice/sessions",
        json={"scenario_id": sc_id},
    )
    assert start_res.status_code == 200
    session = start_res.json()
    session_id = session["id"]
    assert session["scenario_id"] == sc_id
    assert session["status"] == "active"

    # 3. Add turn endpoint
    turn_res = client.post(
        f"/api/conversations/{cid}/practice/sessions/{session_id}/turns",
        json={
            "user_argument": "I was only a passenger in the car and have the right to speak to an advocate under BNSS 38.",
            "language": "en",
        },
    )
    assert turn_res.status_code == 200
    turn = turn_res.json()
    assert turn["turn_index"] == 1
    assert "opponent_reply" in turn
    assert turn["coach_feedback"]["assessment"] == "strong"

    # 4. Get session endpoint
    get_res = client.get(f"/api/conversations/{cid}/practice/sessions/{session_id}")
    assert get_res.status_code == 200
    assert len(get_res.json()["turns"]) == 1

    # 5. Export actions endpoint
    export_res = client.post(
        f"/api/conversations/{cid}/practice/sessions/{session_id}/export-actions",
        json={
            "action_titles": [
                "Assert right to meet advocate under BNSS Section 38",
                "Request written grounds of arrest under Section 47",
            ]
        },
    )
    assert export_res.status_code == 200
    assert export_res.json()["exported_count"] == 2
    assert export_res.json()["status"] == "completed"

    # Check that user action tracker recorded them
    actions_res = client.get(f"/api/conversations/{cid}")
    assert actions_res.status_code == 200
    tracker_actions = [a["title"] for a in actions_res.json().get("user_actions", [])]
    assert "Assert right to meet advocate under BNSS Section 38" in tracker_actions


def test_roleplay_setup_and_chat_flow(client):
    from tests.conftest import create_case

    cid = create_case(client)

    # 1. Setup endpoint
    setup_res = client.get(f"/api/conversations/{cid}/roleplay/setup")
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert "case_title" in setup_data
    assert "case_synopsis" in setup_data
    assert len(setup_data["stakeholders"]) >= 2

    # 2. Start roleplay session
    start_res = client.post(
        f"/api/conversations/{cid}/roleplay/start",
        json={"stakeholder": "Police officer"},
    )
    assert start_res.status_code == 200
    start_data = start_res.json()
    assert start_data["stakeholder"] == "Police officer"
    assert "What is your relation to the person" in start_data["opening_message"]
    session_id = start_data["session_id"]

    # 3. Chat turn
    chat_res = client.post(
        f"/api/conversations/{cid}/roleplay/chat?session_id={session_id}",
        json={
            "message": "I want to know which court he was produced before and how to get his FIR."
        },
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["turn_index"] == 1
    assert (
        "FIR" in chat_data["reply"]
        or "court" in chat_data["reply"]
        or "documents" in chat_data["reply"]
    )


def test_roleplay_concerned_vs_non_concerned_authority():
    engine = PracticeEngine()
    case_synopsis = (
        "Your brother is in custody and the car has been seized under the Bihar Prohibition Act."
    )

    # Concerned authority
    assert engine.is_concerned_authority("Police officer", case_synopsis) is True
    assert engine.is_concerned_authority("Opposing lawyer", case_synopsis) is True

    # Non-concerned authority
    assert engine.is_concerned_authority("Income Tax Officer", case_synopsis) is False
    assert engine.is_concerned_authority("School Principal", case_synopsis) is False

    # Non-concerned authority authentic response
    unrelated_reply = engine.execute_roleplay_turn(
        "Income Tax Officer",
        case_synopsis,
        [],
        "Please release my brother's car!",
    )
    assert "Income Tax Officer" in unrelated_reply
    assert (
        "thana" in unrelated_reply
        or "police" in unrelated_reply
        or "jurisdiction" in unrelated_reply.lower()
    )


# ---- honesty and live-call behaviour -------------------------------------------------------

import json  # noqa: E402
import re  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.config import Settings  # noqa: E402
from app.practice import engine as engine_module  # noqa: E402

BIHAR_MESSAGE = "My brother was taking his car from Patna and police found alcohol in it in Bihar."


class FakeResponses:
    def __init__(self, text="Show me the seizure memo first.", error=None):
        self.text, self.error, self.calls = text, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if not kwargs.get("stream"):
            return SimpleNamespace(status="completed", output_text=self.text)
        words = self.text.split(" ")
        deltas = [w + (" " if i < len(words) - 1 else "") for i, w in enumerate(words)]
        return iter(
            [SimpleNamespace(type="response.output_text.delta", delta=d) for d in deltas]
            + [SimpleNamespace(type="response.completed", response=SimpleNamespace(usage=None))]
        )


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def live_engine():
    responses = FakeResponses()
    engine = PracticeEngine(
        Settings(openai_api_key="fixture-not-real"),
        client_factory=lambda **_: FakeClient(responses),
    )
    return engine, responses


def test_offline_setup_quotes_the_user_instead_of_inventing_facts():
    engine = PracticeEngine()
    setup = engine.extract_roleplay_setup(None, [BIHAR_MESSAGE], "")
    assert setup["case_title"] == "Liquor case · Bihar"
    assert BIHAR_MESSAGE in setup["case_synopsis"]
    assert "custody" not in setup["case_synopsis"]

    empty = engine.extract_roleplay_setup(None, [], "")
    assert "Tell us about your case" in empty["case_synopsis"]
    assert engine.model_calls == 0


def test_alcohol_outside_bihar_is_not_labelled_a_bihar_case():
    setup = PracticeEngine().extract_roleplay_setup(None, ["The restaurant served alcohol."], "")
    assert "Bihar" not in setup["case_title"]


def test_live_roleplay_sends_the_conversation_in_order(live_engine):
    engine, responses = live_engine
    history = [{"user_argument": "Where is he held?", "opponent_reply": "At this station."}]
    result = engine.roleplay_turn(
        "Police officer",
        "Liquor was found in my brother's car in Bihar.",
        history,
        "Can I see the FIR?",
        "hi",
        opening="Who are you?",
    )
    assert result.reply == "Show me the seizure memo first." and result.in_character
    sent = responses.calls[0]
    assert [(i["role"], i["content"]) for i in sent["input"]] == [
        ("assistant", "Who are you?"),
        ("user", "Where is he held?"),
        ("assistant", "At this station."),
        ("user", "Can I see the FIR?"),
    ]
    assert sent["model"] == engine.settings.openai_chat_model and sent["store"] is False
    assert "Police officer" in sent["instructions"] and "Devanagari" in sent["instructions"]
    assert engine.model_calls == 1


def test_roleplay_is_fast_and_in_character(live_engine):
    engine, responses = live_engine
    responses.text = "Under Section 30 the car will be confiscated."
    result = engine.roleplay_turn("Police officer", BIHAR_MESSAGE, [], "Release the car.")
    # The character may cite law like the real officer would; no extra check or notice.
    assert result.reply == responses.text and result.notice is None
    sent = responses.calls[0]
    assert sent["reasoning"] == {"effort": "low"} and sent["max_output_tokens"] <= 1000
    assert sent["stream"] is True and len(responses.calls) == 1


def test_reply_streams_word_by_word(live_engine):
    engine, responses = live_engine
    events = list(engine.roleplay_stream("Landlord", "Deposit kept.", [], "Return my deposit."))
    deltas = [value for kind, value in events if kind == "delta"]
    assert len(deltas) > 1 and "".join(deltas) == responses.text
    assert events[-1][0] == "done" and events[-1][1].reply == responses.text


def test_reasoning_is_dropped_for_models_that_reject_it(live_engine, monkeypatch):
    import httpx
    from openai import BadRequestError

    engine, responses = live_engine
    monkeypatch.setattr(engine_module, "_NO_REASONING_MODELS", set())
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    rejected = BadRequestError(
        "reasoning not supported", response=httpx.Response(400, request=request), body=None
    )
    real_create = responses.create

    def create(**kwargs):
        if "reasoning" in kwargs:
            responses.calls.append(kwargs)
            raise rejected
        return real_create(**kwargs)

    responses.create = create
    assert engine.roleplay_turn("Landlord", "Deposit kept.", [], "Pay me.").reply
    assert engine.model_calls == 2
    engine.roleplay_turn("Landlord", "Deposit kept.", [], "Pay me.")
    assert "reasoning" not in responses.calls[-1] and engine.model_calls == 3


def test_model_failure_falls_back_to_a_canned_line(live_engine):
    engine, responses = live_engine
    responses.error = RuntimeError("timeout")
    result = engine.roleplay_turn("Landlord", "Deposit not returned.", [], "Return my deposit.")
    assert result.reply == engine_module.CANNED_LINES["landlord"]["en"][1]
    assert engine.model_calls == 1


def test_roleplay_crisis_shows_safety_guidance_not_the_character(live_engine):
    engine, responses = live_engine
    result = engine.roleplay_turn(
        "Police officer", BIHAR_MESSAGE, [], "They are beating him right now"
    )
    assert not result.in_character and result.notice == "safety"
    assert result.reply == safety_event("en", india=True, category="physical_safety")["text"]
    assert responses.calls == []


def test_roleplay_fabrication_request_gets_an_honesty_notice():
    result = PracticeEngine().roleplay_turn(
        "Police officer", BIHAR_MESSAGE, [], "Should I make a fake receipt for the car?"
    )
    assert result.notice == engine_module.FABRICATION_NOTICE


def test_role_matching_does_not_treat_support_officers_as_police():
    assert engine_module._role_key("Customer support officer") == "company"
    assert engine_module._role_key("Company director / Boss") == "employer"
    assert engine_module._role_key("Station House Officer") == "police"


def test_coach_safeguards_are_verified_passages_only():
    engine = PracticeEngine()
    criminal = engine.safeguards("criminal")
    assert [s.passage_id for s in criminal] == list(engine_module.SAFEGUARD_PASSAGES["criminal"])
    assert all(s.canonical_url and s.relevance for s in criminal)
    assert engine.safeguards("tenancy") == []


def test_scenarios_use_placeholders_for_facts_and_no_unsourced_sections():
    engine = PracticeEngine()
    for words in (
        BIHAR_MESSAGE,
        "refund refused on amazon",
        "landlord kept my deposit",
        "unpaid salary",
    ):
        for scenario in engine.generate_scenarios(None, recent_messages=[words]):
            assert "[" in (scenario.suggested_first_response or ""), scenario.scenario_id
            unsourced = " ".join(
                [
                    scenario.opening_statement,
                    scenario.objective,
                    scenario.suggested_first_response or "",
                ]
            )
            assert not re.search(r"\b(?:section|rule)\s*\d", unsourced, re.I), scenario.scenario_id


def test_roleplay_session_keeps_the_synopsis_and_counts_model_calls(client, monkeypatch):
    from app.main import app
    from tests.conftest import create_case

    cid = create_case(client)
    start = client.post(
        f"/api/conversations/{cid}/roleplay/start",
        json={"stakeholder": "Landlord", "case_title": "Deposit", "case_synopsis": "Deposit kept."},
    ).json()
    assert start["case_synopsis"] == "Deposit kept."
    session = client.get(f"/api/conversations/{cid}/practice/sessions/{start['session_id']}").json()
    assert session["objective"] == "Deposit kept."

    recorded = []
    monkeypatch.setattr(app.state.abuse, "record_turn_usage", lambda *a, **k: recorded.append(a))
    chat = client.post(
        f"/api/conversations/{cid}/roleplay/chat?session_id={start['session_id']}",
        json={"message": "Please return it."},
    ).json()
    assert chat["in_character"] is True and chat["notice"] is None
    assert recorded and recorded[0][1] == 0  # offline: no model calls


def test_roleplay_respects_the_model_call_circuit_breaker(client, monkeypatch):
    from app.main import app
    from tests.conftest import create_case

    cid = create_case(client)
    monkeypatch.setattr(
        app.state.abuse,
        "check_circuit_breaker",
        lambda *a, **k: (False, "device_model_call_circuit_open"),
    )
    response = client.get(f"/api/conversations/{cid}/roleplay/setup")
    assert response.status_code == 503


def test_streamed_roleplay_chat_endpoint(client):
    from tests.conftest import create_case

    cid = create_case(client)
    start = client.post(
        f"/api/conversations/{cid}/roleplay/start",
        json={"stakeholder": "Police officer", "case_synopsis": "My brother was arrested."},
    ).json()
    response = client.post(
        f"/api/conversations/{cid}/roleplay/chat/stream?session_id={start['session_id']}",
        json={"message": "Where is he held?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [f for f in response.text.split("\n\n") if f.startswith("event: result")]
    result = json.loads(frames[0].split("data: ", 1)[1])
    assert result["turn_index"] == 1 and result["in_character"] is True
    saved = client.get(f"/api/conversations/{cid}/practice/sessions/{start['session_id']}").json()
    assert saved["turns"][0]["opponent_reply"] == result["reply"]


def test_reopening_roleplay_setup_reuses_the_summary(client, monkeypatch):
    from tests.conftest import create_case

    cid = create_case(client)
    calls = []
    original = PracticeEngine.extract_roleplay_setup

    def counting(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PracticeEngine, "extract_roleplay_setup", counting)
    first = client.get(f"/api/conversations/{cid}/roleplay/setup").json()
    second = client.get(f"/api/conversations/{cid}/roleplay/setup").json()
    assert first == second and len(calls) == 1


def test_persona_setup_writes_the_opening_line_in_character(live_engine):
    engine, responses = live_engine
    responses.text = "Haan, boliye. Kis silsile mein aaye ho?"
    opening = engine.get_opening_message("Police officer", "My brother was arrested.", "hinglish")
    assert opening == responses.text
    sent = responses.calls[0]
    assert "You are Police officer" in sent["instructions"]
    assert "My brother was arrested." in sent["instructions"]
    assert "Hinglish" in sent["instructions"] and sent["input"][0]["role"] == "developer"


def test_opening_falls_back_to_a_canned_line_offline():
    opening = PracticeEngine().get_opening_message("Landlord", "Deposit kept.")
    assert opening == engine_module.CANNED_LINES["landlord"]["en"][0]
