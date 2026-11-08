"""Unit tests for Nyay Saathi Practice Section (Engine, Safety Interceptors, Database)."""

from __future__ import annotations

import pytest

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
            "issue": CaseFact(key="issue", value="brother arrested with car carrying liquor in bihar", status="user_allegation"),
            "location": CaseFact(key="location", value="patna to biharsharif", status="user_allegation"),
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
    assert "Bihar" in s.opening_statement or "Prohibition" in s.opening_statement
    assert "BNSS Section 38" in " ".join(s.key_rights)
    assert s.opponent_role == "Investigating Officer (Sub-Inspector)"


def test_scenario_generation_consumer_case():
    engine = PracticeEngine()
    memory = CaseMemory(
        version=1,
        domain="consumer",
        facts={
            "product": CaseFact(key="product", value="defective phone bought on amazon refund rejected", status="user_allegation"),
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
    user_argument = "They are beating him right now in the station and I want to kill myself please help"
    opponent_reply, feedback = engine.evaluate_and_respond(scenario, [], user_argument)

    assert feedback.is_crisis is True
    assert "112" in (feedback.crisis_text or "")
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
    user_argument = "Can I just create a fake receipt and lie to police that I was never in the car?"
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
    assert any(s.section == "Section 38" for s in feedback.statutory_safeguards)


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
    assert any("Consumer Protection (E-Commerce) Rules" in s.act for s in feedback.statutory_safeguards)


def test_database_practice_session_and_turns(tmp_path):
    db = Database(tmp_path / "test.db", cipher=EnvelopeCipher("0" * 32, "test-key"), encrypt=True)
    with db.connect() as c:
        c.execute("INSERT INTO owners VALUES ('owner-1', 'token-1', '2026-11-08T00:00:00Z')")
        c.execute("INSERT INTO conversations VALUES ('c1', 'owner-1', 'Car Case', 'en', '2026-11-08T00:00:00Z', '2026-11-08T00:00:00Z', NULL)")

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
        "statutory_safeguards": [{"section": "38", "act": "BNSS", "title": "Lawyer", "relevance": "Meet lawyer"}],
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
    assert turn["user_argument"] == "I was only a passenger and have right to an advocate under BNSS 38."

    # 3. Retrieve session with decrypted turns
    retrieved = db.get_practice_session("owner-1", "c1", session["id"])
    assert len(retrieved["turns"]) == 1
    assert retrieved["turns"][0]["user_argument"] == "I was only a passenger and have right to an advocate under BNSS 38."
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
    assert "What information do you need" in start_data["opening_message"]
    session_id = start_data["session_id"]

    # 3. Chat turn
    chat_res = client.post(
        f"/api/conversations/{cid}/roleplay/chat?session_id={session_id}",
        json={"message": "I want to know which court he was produced before and how to get his FIR."},
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["turn_index"] == 1
    assert "FIR" in chat_data["reply"] or "court" in chat_data["reply"] or "documents" in chat_data["reply"]


def test_roleplay_concerned_vs_non_concerned_authority():
    engine = PracticeEngine()
    case_synopsis = "Your brother is in custody and the car has been seized under the Bihar Prohibition Act."

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
    assert "thana" in unrelated_reply or "police" in unrelated_reply or "jurisdiction" in unrelated_reply.lower()


