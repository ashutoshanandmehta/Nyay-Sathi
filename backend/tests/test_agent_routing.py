"""Offline orchestration evaluations. Scripted decisions are NOT model accuracy evidence."""

from types import SimpleNamespace

import pytest

from app.agent.budget import TurnBudget
from app.agent.contracts import ApplicabilityAssessment, ResearchRequest, RouteDecision
from app.agent.routing import assess_research_escalation, prepare_route
from app.config import Settings
from tests.conftest import create_case
from tests.test_primary_agent import ScriptedProvider, answer, install, post

SCENARIOS = [
    ("greeting", "नमस्ते, मदद चाहिए।", "fast"),
    ("earbuds", "₹5,000 के earbuds खराब हैं, refund चाहिए।", "verified"),
    ("refund", "Refund pending hai; company ko email kar diya.", "verified"),
    ("delivery", "My paid order never arrived.", "verified"),
    ("service", "Repair service failed twice. What can I do?", "verified"),
    ("draft_edit", "Confirmed draft ko सरल हिंदी में लिखो।", "fast"),
    ("correction", "Amount ₹5000 था, ₹15000 नहीं।", "fast"),
    ("missing_date", "पुरानी खरीद पर कौन सा नियम लगेगा?", "verified"),
    ("jurisdiction", "I moved from Delhi to Pune; where can I complain?", "verified"),
    ("new_law", "Has the consumer filing rule changed this week?", "research"),
    ("stale_source", "That source is from 2019; is it still current?", "research"),
    ("conflict", "Two official pages give different filing instructions.", "research"),
    ("misleading", "A blog guarantees ten times compensation. Is that true?", "research"),
    ("banking", "My bank rejected an unauthorized transaction claim.", "verified"),
    ("unsupported", "Can you guarantee my foreign tax appeal outcome?", "verified"),
]


def decision(route, **updates):
    return RouteDecision(
        route=route,
        reason="Assess evidence applicability",
        existing_evidence_sufficient=route == "fast",
        applicability_uncertain=route == "verified",
        **updates,
    )


def assessment(**updates):
    return ApplicabilityAssessment(
        jurisdiction="India; state unconfirmed",
        relevant_date="Unknown",
        limitations=["Incident date is not confirmed"],
        excluded_evidence_ids=[],
        **updates,
    )


def request():
    return ResearchRequest(
        questions=[
            {
                "query": "India consumer complaint official filing procedure",
                "material_gap": "Current official procedure is missing",
            }
        ],
        fresh_required=True,
    )


def setup(outputs, message="Help me", settings=None):
    settings = settings or Settings(_env_file=None, openai_api_key="fixture-not-real")
    state = {"current_message": message, "memory": {}, "passages": [], "tool_records": []}
    events, searches = [], []

    def research(req, state, budget):
        searches.append(req)
        return {"evidence": [], "limitations": ["Fixture contains no public evidence"]}

    agent = SimpleNamespace(
        settings=settings,
        provider=ScriptedProvider(*outputs),
        _context=lambda s: {"current_message": s["current_message"], "evidence": s["passages"]},
        research=SimpleNamespace(run=research),
    )

    def event(stage, status="running", **extra):
        events.append({"stage": stage, "status": status, **extra})

    return agent, state, TurnBudget(settings), event, events, searches


@pytest.mark.parametrize("name,message,route", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_scenario_branch_executes_required_work(name, message, route):
    d = decision(route, research=request() if route == "research" else None)
    outputs = [d] + ([assessment()] if route != "fast" else [])
    agent, state, budget, emit, events, searches = setup(outputs, message)
    prepare_route(agent, state, budget, emit)
    assert state["route"] == route
    assert bool(searches) == (route == "research")
    assert any(e["stage"] == "applicability" for e in events) == (route != "fast")
    assert budget.requests == (1 if route == "fast" else 2)
    assert all(k[1]["allow_tools"] is False for k in agent.provider.requests)


def test_unsafe_fast_promotes_and_excludes_old_evidence():
    d = decision("fast").model_copy(update={"applicability_uncertain": True})
    a = assessment().model_copy(update={"excluded_evidence_ids": ["old"]})
    agent, state, budget, emit, events, _ = setup([d, a])
    state["passages"] = [{"passage_id": "old", "text": "Stale law"}]
    prepare_route(agent, state, budget, emit)
    assert state["route"] == "verified" and state["passages"] == []
    assert state["excluded_evidence_ids"] == ["old"]


def test_verified_escalates_once_even_when_research_cannot_fill_gap():
    a = assessment(research=request())
    agent, state, budget, emit, events, searches = setup([decision("verified"), a, a])
    prepare_route(agent, state, budget, emit)
    assert len(searches) == 1
    assert state["route_history"] == ["verified", "research"]
    assert state["route_guidance"]["limitations"]


def test_late_research_is_assessed_and_bad_evidence_removed():
    a = assessment().model_copy(update={"excluded_evidence_ids": ["wrong-state"]})
    agent, state, budget, emit, events, _ = setup([a])
    state["passages"] = [{"passage_id": "wrong-state"}]
    result = assess_research_escalation(agent, state, budget, emit)
    assert state["passages"] == [] and result["excluded_evidence_ids"] == ["wrong-state"]


def test_low_budget_does_not_start_unreviewable_route():
    agent, state, budget, emit, _, _ = setup(
        [decision("fast")], settings=Settings(_env_file=None, agent_max_requests=4)
    )
    with pytest.raises(ValueError, match="allowance"):
        prepare_route(agent, state, budget, emit)
    assert budget.requests == 0


@pytest.mark.parametrize("route", ["fast", "verified", "research"])
def test_real_api_runs_routing_and_persists_actual_events(client, isolated_app, route):
    cid = create_case(client)
    d = decision(route, research=request() if route == "research" else None)
    outputs = [d] + ([assessment()] if route != "fast" else []) + [answer()]
    provider = ScriptedProvider(*outputs)
    research = SimpleNamespace(run=lambda *args: {"evidence": [], "limitations": ["Fixture only"]})
    runner = install(isolated_app, provider, research)
    runner.settings.agent_routing_enabled = True
    response = post(client, cid, "I paid for a product.")
    assert response.status_code == 200
    # API persists metrics and stream events in message metadata.
    detail = client.get(f"/api/conversations/{cid}").json()
    metadata = detail["messages"][-1]["metadata"]
    assert metadata["metrics"]["route"] == route
    assert metadata["metrics"]["route_history"] == [route]
    assert not provider.outputs


def test_urgent_guidance_precedes_router_failure(client, isolated_app):
    cid = create_case(client)
    runner = install(isolated_app, ScriptedProvider(TimeoutError("fixture router timeout")))
    runner.settings.agent_routing_enabled = True
    response = post(client, cid, "India mein UPI fraud hua, paise abhi kat rahe hain", stream=True)
    assert response.status_code == 200
    assert response.text.index("event: safety") < response.text.index('"stage": "routing"')
    detail = client.get(f"/api/conversations/{cid}").json()
    assert len(detail["safety_messages"]) == 1
    assert "1930" in detail["safety_messages"][0]["text"]


def test_hindi_earbuds_retrieves_real_nch_sources_without_network():
    """Regression for the live failure: the consumer corpus never reached preflight."""
    from app.agent.runner import PrimaryAgent
    from app.rag.retrieval import HybridRetriever

    settings = Settings(_env_file=None, openai_api_key=None)
    agent = PrimaryAgent(settings, HybridRetriever(settings))
    state = {
        "current_message": SCENARIOS[1][1] + " कंपनी और दुकानदार पैसे वापस नहीं दे रहे।",
        "memory": {},
        "passages": [],
        "tool_records": [],
    }
    agent._pre_retrieve_certified(state)
    by_id = {p["passage_id"]: p for p in state["passages"]}
    assert "nch-prelitigation" in by_id
    nch = by_id["nch-prelitigation"]
    assert nch["retrieved_at"] == "2026-11-20" and "1915" in nch["text"]
    assert nch["origin"] == "corpus" and not nch["certified_proposition"]
    assert "consumeraffairs.gov.in" in nch["canonical_url"]


def test_primary_preserves_publication_time_instead_of_repeating_research(isolated_app):
    provider = ScriptedProvider(answer())
    runner = install(isolated_app, provider)
    runner.settings.agent_routing_enabled = True
    runner.settings.agent_deadline_seconds = 58
    now = [0.0]
    budget = TurnBudget(runner.settings, clock=lambda: now[0])
    now[0] = 30.0
    state = {
        "current_message": "I paid for a product.",
        "memory": {},
        "passages": [],
        "language": "hi",
        "routing_research_attempted": True,
    }
    runner._reason(state, budget, lambda *a, **k: None, lambda *a, **k: None)
    assert provider.requests[0][1]["allow_tools"] is False
    assert budget.remaining_time() == 28.0


def test_verified_reuses_router_assessment_but_research_requires_fresh_check():
    a = assessment()
    d = decision("verified").model_copy(update={"applicability": a})
    agent, state, budget, emit, events, searches = setup([d])
    prepare_route(agent, state, budget, emit)
    assert budget.requests == 1
    assert state["route_guidance"]["jurisdiction"] == a.jurisdiction
    assert any(e["stage"] == "applicability" and e["status"] == "complete" for e in events)

    d = decision("research", research=request()).model_copy(update={"applicability": a})
    fresh = assessment().model_copy(update={"limitations": ["Fresh source assessment"]})
    agent, state, budget, emit, events, searches = setup([d, fresh])
    prepare_route(agent, state, budget, emit)
    assert budget.requests == 2 and len(searches) == 1
    assert state["route_guidance"]["limitations"] == ["Fresh source assessment"]
