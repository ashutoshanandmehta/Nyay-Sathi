"""Web search costs less: a small search model works, a follow-up reuses pages already cited, and
an offline report shows which pages are worth adding to the packs.

Offline: fake OpenAI client and scripted model outputs; no network call.
"""

import json
import sqlite3

import httpx
import pytest
from openai import BadRequestError

from app.agent.contracts import AgentAnswer, AnswerClaim
from app.config import Settings
from app.services import web_research
from app.services.context_builder import ContextBuilder
from scripts.report_search_gaps import report
from tests.conftest import create_case
from tests.test_answer_quality import _post, _research_with, _task
from tests.test_primary_agent import ScriptedProvider, install
from tests.test_repair_and_drafts import _review, _verdict

VIGILANCE = {
    "source_id": "web-vigilance",
    "passage_id": "web-vigilance-official-webpage-0-abc",
    "title": "Vigilance Investigation Bureau, Bihar",
    "locator": "Official webpage",
    "text": "Complaints about corruption by public servants can be made to the Vigilance Investigation Bureau, Patna.",
    "canonical_url": "https://state.bihar.gov.in/vigilance",
    "retrieved_at": "2026-11-09T08:01:03+00:00",
    "limitations": "Official webpage; applicability to the user's facts needs review.",
    "origin": "web",
    "source_type": "indian_official",
    "verification_status": "origin_checked_applicability_pending",
    "jurisdiction": "India",
}


class FakeResponses:
    def __init__(self, calls, reject_reasoning):
        self.calls, self.reject_reasoning = calls, reject_reasoning

    def create(self, **request):
        self.calls.append(request)
        if self.reject_reasoning and "reasoning" in request:
            response = httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
            raise BadRequestError("Unsupported parameter: 'reasoning.effort'", response=response, body=None)
        output = [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {"type": "search", "sources": [{"type": "url", "url": "https://indiacode.nic.in/act.pdf"}]},
            }
        ]
        return type("Response", (), {"model_dump": lambda self, mode: {"output": output, "usage": {}}})()


@pytest.fixture
def fake_openai(monkeypatch):
    calls = []

    def factory(reject_reasoning):
        class Client:
            def __init__(self, **_):
                self.responses = FakeResponses(calls, reject_reasoning)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(web_research, "OpenAI", Client)
        monkeypatch.setattr(web_research.OfficialSearchProvider, "no_reasoning_models", set())
        return calls

    return factory


def test_a_small_search_model_without_reasoning_still_finds_links(fake_openai):
    calls = fake_openai(reject_reasoning=True)
    provider = web_research.OfficialSearchProvider(
        Settings(openai_api_key="fixture", openai_web_search_model="gpt-4o-mini")
    )

    found, _ = provider.search_public("bihar vigilance bureau corruption complaint", 10)
    assert found  # the link still comes back
    assert ["reasoning" in c for c in calls] == [True, False]  # rejected once, retried without

    provider.search_public("bihar land mutation application", 10)
    assert "reasoning" not in calls[-1]  # remembered: no wasted rejected call next time
    assert len(calls) == 3


def test_a_reasoning_search_model_keeps_its_setting(fake_openai):
    calls = fake_openai(reject_reasoning=False)
    provider = web_research.OfficialSearchProvider(Settings(openai_api_key="fixture"))
    provider.search_public("bns section 351 criminal intimidation", 10)
    assert calls[0]["reasoning"] == {"effort": "low"} and len(calls) == 1


def test_devspace_offers_a_small_search_model():
    from app.api.devspace import MODEL_OPTIONS

    assert "gpt-4o-mini" in MODEL_OPTIONS["OPENAI_WEB_SEARCH_MODEL"]


def test_earlier_cited_official_pages_are_collected_newest_first():
    older = {**VIGILANCE, "passage_id": "web-older", "citation_number": 1}
    recent = [
        {"role": "assistant", "metadata": {"sources": [older]}},
        {"role": "user", "content": "And then?"},
        {
            "role": "assistant",
            "metadata": {
                "sources": [
                    {**VIGILANCE, "citation_number": 2},
                    {**VIGILANCE, "passage_id": "pack-bns-2023-s351", "origin": "official_pack"},
                ]
            },
        },
    ]
    found = ContextBuilder.prior_web_sources(recent)
    assert [s["passage_id"] for s in found] == [VIGILANCE["passage_id"], "web-older"]
    assert "citation_number" not in found[0]  # numbers belong to the old message


def test_a_follow_up_can_cite_an_earlier_page_without_searching_again(client, isolated_app):
    cid = create_case(client)

    def turn(text, evidence):
        return AgentAnswer(
            central_question="q",
            tasks=[_task()],
            claims=[
                AnswerClaim(
                    claim_id="vb",
                    task_id="task-1",
                    kind="procedure",
                    block_type="recommended_route",
                    grounding="verified_legal_source",
                    text=text,
                    evidence_ids=evidence,
                )
            ],
        )

    first = turn("You can complain to the Vigilance Investigation Bureau in Patna.", [VIGILANCE["passage_id"]])
    second = turn("Send the same written complaint to the Bureau in Patna.", [VIGILANCE["passage_id"]])
    provider = ScriptedProvider(first, _review(_verdict("vb")), second, _review(_verdict("vb")))
    runner = install(isolated_app, provider, _research_with(VIGILANCE))
    _post(client, cid, "Police took money from us in Patna. Where do we complain?")

    runner.research = _research_with()  # nothing local this time, and no search is scripted
    reply = _post(client, cid, "How do we follow up with them?").json()["assistant_message"]

    sent = json.loads(provider.requests[2][0][0]["content"])
    assert VIGILANCE["passage_id"] in [e.get("evidence_id") for e in sent["evidence"]]
    assert "Send the same written complaint to the Bureau in Patna." in reply["content"]
    assert len(provider.requests) == 4  # answer + review per turn; no research round


def test_search_report_lists_repeatedly_cited_pages_and_search_cost(tmp_path):
    db = tmp_path / "app.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE messages (role TEXT, metadata_json TEXT)")
    conn.execute("CREATE TABLE model_call_events (request_id TEXT, payload_json TEXT)")
    for _ in range(2):
        conn.execute(
            "INSERT INTO messages VALUES ('assistant', ?)", (json.dumps({"sources": [VIGILANCE]}),)
        )
    for request_id in ("r1", "r1", "r2"):
        conn.execute(
            "INSERT INTO model_call_events VALUES (?, ?)",
            (request_id, json.dumps({"stage": "web_search", "usage_reported": {"input_tokens": 12000}})),
        )
    conn.commit()
    conn.close()

    text = report(db)
    assert "web searches: 3" in text and "12,000 per search" in text
    assert "| 2 | state.bihar.gov.in |" in text  # cited twice: a pack candidate
