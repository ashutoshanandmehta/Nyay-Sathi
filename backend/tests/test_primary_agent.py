"""New runner tests. Provider fixtures test software behavior, not model/legal accuracy."""

import copy
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import pytest

from app.agent.budget import TurnBudget
from app.agent.contracts import (
    AgentAnswer,
    AgentReview,
    AgentTask,
    AnswerClaim,
    ClaimVerdict,
    ResearchRequest,
)
from app.agent.provider import ResponsesProvider
from app.agent.research import (
    EvidenceCache,
    ResearchService,
    authority,
    canonical_url,
    rank_passages,
)
from app.agent.runner import PrimaryAgent
from app.agent.safety import safety_event, urgent_trigger
from app.agent.verification import mechanical_checks, propagate_dependencies
from app.answers.evidence import EvidenceRegistry
from app.config import Settings
from app.memory.patches import CasePatch, PatchValue, PatchVerdict
from app.routing.segments import segment_message
from app.services.model_calls import BudgetExhausted, model_calls
from tests.conftest import create_case


class ScriptedProvider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.requests = []

    def complete(self, items, instructions, budget, **kwargs):
        self.requests.append((copy.deepcopy(items), kwargs))
        budget.reserve("fixture")
        with model_calls.operation(kwargs.get("stage", "primary"), "fixture") as event:
            event["usage_reported"] = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}
            budget.report(event["usage_reported"])
            output = self.outputs.pop(0)
            if isinstance(output, Exception):
                raise output
            if isinstance(output, tuple):
                return output
            return [], [], output


def answer(
    message="I paid for a product.",
    *,
    kind="quote",
    text=None,
    domain="consumer",
    intent="summary",
    case_link="new",
):
    segments = segment_message(message)
    return AgentAnswer(
        central_question="What useful assistance is requested?",
        tasks=[
            AgentTask(
                task_id="task-1",
                title="Factual summary",
                intent=intent,
                domain=domain,
                case_link=case_link,
                relationship="reported relationship",
                source_segment_ids=[s["id"] for s in segments],
            )
        ],
        claims=[
            AnswerClaim(
                claim_id="claim-1",
                task_id="task-1",
                kind=kind,
                text=text if text is not None else message,
                evidence_ids=["segment:" + segments[0]["id"]],
            )
        ],
    )


def install(isolated_app, provider, research=None):
    settings = isolated_app.state.settings.model_copy(update={"openai_api_key": "fixture-not-real"})
    isolated_app.state.settings = settings
    runner = PrimaryAgent(
        settings, isolated_app.state.retriever, provider=provider, research=research
    )
    isolated_app.state.assistant_graph = runner
    return runner


def post(client, cid, content, request_id=None, stream=False):
    return client.post(
        f"/api/conversations/{cid}/turns" + ("/stream" if stream else ""),
        json={"content": content, "request_id": request_id or str(uuid.uuid4())},
    )


def test_one_call_quote_path_persists_and_replays_without_new_model(client, isolated_app):
    cid = create_case(client)
    provider = ScriptedProvider(answer())
    install(isolated_app, provider)
    request = str(uuid.uuid4())
    result = post(client, cid, "I paid for a product.", request)
    assert result.status_code == 200, result.text
    data = result.json()
    assert "You report:" in data["assistant_message"]["content"]
    assert data["case_version"] == 0
    assert data["assistant_message"]["metadata"]["metrics"]["provider_requests_reserved"] == 1
    assert not data["verification"]["independent_review_performed"]
    assert post(client, cid, "I paid for a product.", request).json() == data
    assert len(provider.requests) == 1
    assert post(client, cid, "Changed request", request).status_code == 409


def test_reviewed_patch_commits_once_and_preserves_provenance(client, isolated_app):
    cid = create_case(client)
    proposed = answer()
    proposed.case_patches = [
        CasePatch(
            patch_id="p1",
            task_id="task-1",
            operation="fact",
            payload=PatchValue(key="problem", value="I paid for a product."),
            source_refs=proposed.claims[0].evidence_ids,
        )
    ]
    review = AgentReview(
        claims=[],
        patch_verdicts=[PatchVerdict(patch_id="p1", support="supported", reason="Exact report")],
        primary_question_answered=True,
        next_action_useful=True,
    )
    provider = ScriptedProvider(proposed, review)
    install(isolated_app, provider)
    request = str(uuid.uuid4())
    result = post(client, cid, "I paid for a product.", request)
    assert result.status_code == 200, result.text
    assert result.json()["case_version"] == 1
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["case_memory"]["facts"]["problem"]["provenance"][0]["source_type"] == "message"
    post(client, cid, "I paid for a product.", request)
    assert len(provider.requests) == 2


def test_general_education_never_commits_even_if_reviewer_approves_patch(client, isolated_app):
    cid = create_case(client)
    message = "Explain an educational legal concept."
    proposed = answer(message, intent="information", case_link="unrelated", domain="other_legal")
    proposed.case_patches = [
        CasePatch(
            patch_id="p1",
            task_id="task-1",
            operation="fact",
            payload=PatchValue(key="bad", value=message),
            source_refs=proposed.claims[0].evidence_ids,
        )
    ]
    review = AgentReview(
        claims=[],
        patch_verdicts=[
            PatchVerdict(patch_id="p1", support="supported", reason="Incorrect proposed permission")
        ],
        primary_question_answered=True,
        next_action_useful=True,
    )
    install(isolated_app, ScriptedProvider(proposed, review))
    result = post(client, cid, message)
    assert result.status_code == 200
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["case_memory"]["version"] == 0 and detail["case_memory"]["facts"] == {}
    assert detail["staged_patches"]


def test_review_failure_preserves_quote_and_withholds_unsupported_legal_claim(client, isolated_app):
    cid = create_case(client)
    proposed = answer()
    proposed.claims.append(
        AnswerClaim(
            claim_id="bad",
            task_id="task-1",
            kind="practical",
            text="The authority must refund in 3 days.",
            evidence_ids=proposed.claims[0].evidence_ids,
        )
    )
    install(isolated_app, ScriptedProvider(proposed, TimeoutError()))
    result = post(client, cid, "I paid for a product.")
    assert result.status_code == 200
    content = result.json()["assistant_message"]["content"]
    assert "You report:" in content and "must refund" not in content
    assert result.json()["assistant_message"]["metadata"]["publication_status"] == "partial"


def test_disguised_law_needs_public_evidence_even_with_supported_review(client, isolated_app):
    cid = create_case(client)
    proposed = answer(kind="practical", text="The authority must refund in 3 days.")
    review = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="claim-1",
                support="supported",
                reason="External claim",
                requires_public_evidence=True,
            )
        ],
        primary_question_answered=True,
        next_action_useful=True,
    )
    runner = install(isolated_app, ScriptedProvider(proposed, review))
    runner.settings.agent_max_rounds = 1
    result = post(client, cid, "I paid for a product.")
    assert "must refund" not in result.json()["assistant_message"]["content"]


def test_safety_is_durable_before_provider_failure_and_deduplicated(client, isolated_app):
    cid = create_case(client)
    install(isolated_app, ScriptedProvider(TimeoutError()))
    message = "Police entered our room in India and demand money now."
    result = post(client, cid, message, stream=True)
    assert result.status_code == 200
    assert result.text.index("event: safety") < result.text.index("event: result")
    detail = client.get(f"/api/conversations/{cid}").json()
    assert len(detail["safety_messages"]) == 1
    assert "112" in detail["safety_messages"][0]["text"]
    assert (
        detail["messages"][-1]["metadata"]["safety_messages"][0]["content_id"]
        == detail["safety_messages"][0]["content_id"]
    )


def test_tool_continuation_preserves_reasoning_and_passes_evidence(client, isolated_app):
    cid = create_case(client)
    request = ResearchRequest(
        questions=[
            {
                "query": "India employment unpaid wages complaint Maharashtra",
                "material_gap": "Applicable wage recovery authority",
            }
        ]
    )
    output = [
        {"type": "reasoning", "id": "r1", "encrypted_content": "opaque"},
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "research_legal_issue",
            "arguments": request.model_dump_json(),
        },
    ]
    message = "My employer owes wages."
    provider = ScriptedProvider((output, [output[1]], None), answer(message, domain="employment"))
    seen = []
    research = SimpleNamespace(
        run=lambda req, state, budget: seen.append(req)
        or {"status": "no_supporting_evidence", "evidence": [], "limitations": ["Offline fixture"]}
    )
    install(isolated_app, provider, research)
    result = post(client, cid, message)
    assert result.status_code == 200
    continuation = provider.requests[1][0]
    assert output[0] in continuation
    assert continuation[-1]["call_id"] == "call-1"
    assert json.loads(continuation[-1]["output"])["limitations"] == ["Offline fixture"]
    assert len(seen) == 1


def test_malformed_tool_and_provider_refusal_have_bounded_fallback(client, isolated_app):
    cid = create_case(client)
    call = {
        "type": "function_call",
        "call_id": "bad",
        "name": "research_legal_issue",
        "arguments": "not json",
    }
    provider = ScriptedProvider(([call], [call], None), ValueError("refused"))
    install(isolated_app, provider)
    result = post(client, cid, "Help with my legal question.")
    assert result.status_code == 200
    assert len(provider.requests) == 2
    assert "could not verify" in result.json()["assistant_message"]["content"]


@pytest.mark.parametrize(
    "message",
    [
        "Hypothetically police entered a room",
        "Last year police entered my room",
        "I am not in danger; what if police entered?",
    ],
)
def test_hypothetical_and_historical_safety_does_not_trigger(message):
    assert not urgent_trigger(message)


def test_stale_contact_is_not_displayed_and_hindi_guidance_remains():
    event = safety_event("hi", today=date(2026, 12, 1), india=True)
    assert "112" not in event["text"] and "सुरक्षा" in event["text"]


def test_budget_is_atomic_and_reserves_finalization():
    settings = Settings(openai_api_key=None, agent_max_requests=3)
    budget = TurnBudget(settings)

    def consume():
        try:
            budget.reserve("fixture", reserve=2)
            return True
        except BudgetExhausted:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: consume(), range(20))) == 1
    assert budget.requests == 1 and budget.available(2)


def test_spend_cap_requires_prices_and_counts_failed_reserved_attempt():
    budget = TurnBudget(Settings(openai_api_key=None, agent_max_cost_usd=0.01))
    with pytest.raises(BudgetExhausted):
        budget.reserve("unknown")
    assert budget.requests == 0
    budget = TurnBudget(Settings(openai_api_key=None))
    budget.reserve("fixture")
    budget.report(None)
    assert budget.snapshot()["cost_status"] == "unknown" and budget.requests == 1


def test_mechanical_gate_rejects_urls_wrong_ids_and_cycles():
    message = "I paid for a product."
    state = {"current_message": message, "message_id": "m", "memory": {}}
    registry = EvidenceRegistry(state)
    a = answer()
    a.claims[0].evidence_ids = ["missing"]
    assert mechanical_checks(a, registry)[0]
    a = answer(text="https://invented.example")
    assert mechanical_checks(a, registry)[0]
    a = answer()
    a.claims[0].depends_on = ["other"]
    a.claims.append(
        AnswerClaim(
            claim_id="other",
            task_id="task-1",
            kind="quote",
            text=message,
            evidence_ids=a.claims[0].evidence_ids,
            depends_on=["claim-1"],
        )
    )
    assert propagate_dependencies(a, {"claim-1": "yes", "other": "yes"}) == {}


def passage(
    source="s1",
    url="https://labour.maharashtra.gov.in/test",
    text="Unpaid wages employment complaint Maharashtra",
):
    return {
        "source_id": source,
        "passage_id": source + "-p1",
        "canonical_url": url,
        "text": text,
        "title": "Synthetic official-page fixture",
        "locator": "Fixture passage",
        "retrieved_at": "2026-11-07T00:00:00+00:00",
        "origin": "web",
    }


def test_cache_expires_and_never_accepts_private_evidence(tmp_path):
    clock = [100.0]
    cache = EvidenceCache(tmp_path / "cache.sqlite3", ttl=10, clock=lambda: clock[0])
    cache.put("public", [passage()])
    assert cache.get("public")
    clock[0] = 111
    assert cache.get("public") is None
    with pytest.raises(ValueError):
        cache.put("private", [{**passage(), "origin": "private"}])


def test_ranking_dedup_and_foreign_authority_separation():
    assert authority("https://www.fda.gov/test")[1] is None
    assert authority("https://labour.maharashtra.gov.in/test")[1] == "India"
    assert canonical_url("https://x.gov.in/a/?utm_source=z#foo") == "https://x.gov.in/a"
    p = passage()
    assert (
        len(rank_passages([p, {**p, "passage_id": "duplicate"}], "unpaid wages employment", 5)) == 1
    )


def test_research_queries_and_hosts_execute_concurrently_with_private_query_rejection(tmp_path):
    settings = Settings(
        database_path=tmp_path / "app.sqlite3", openai_api_key="fixture", agent_max_requests=6
    )
    search_barrier, fetch_barrier = threading.Barrier(2), threading.Barrier(2)

    class Provider:
        def search_public(self, query, timeout):
            search_barrier.wait(timeout=2)
            domain = "labour.maharashtra.gov.in" if "wages" in query else "sci.gov.in"
            return [{"url": "https://" + domain + "/test"}], {"total_tokens": 10}

    class Fetcher:
        def read(self, candidate, timeout):
            fetch_barrier.wait(timeout=2)
            p = passage(
                source=candidate["url"],
                url=candidate["url"],
                text="Employment wages complaint and judicial remedies workers",
            )
            return {
                "url": candidate["url"],
                "passages": [p],
                "source_id": p["source_id"],
                "raw": b"public",
                "hash": "fixture",
            }

    service = ResearchService(
        settings,
        SimpleNamespace(passages=[]),
        provider=Provider(),
        fetcher=Fetcher(),
        repository=SimpleNamespace(save=lambda *a: None),
    )
    request = ResearchRequest(
        questions=[
            {"query": "India unpaid wages complaint", "material_gap": "Wage authority"},
            {"query": "India employment judicial remedies", "material_gap": "Judicial remedy"},
        ]
    )
    state = {
        "current_message": "My name is Private Person. My wages are unpaid.",
        "context": {},
        "owner_id": "o",
        "conversation_id": "c",
        "request_id": "r",
    }
    result = service.run(request, state, TurnBudget(settings))
    assert len(result["evidence"]) >= 1
    assert sum(r["tool"] == "web_search" for r in result["tool_records"]) == 2
    rejected = ResearchRequest(
        questions=[
            {"query": "Private Person unpaid wages complaint", "material_gap": "Private identity"}
        ]
    )
    result = service.run(rejected, state, TurnBudget(settings))
    assert not result["evidence"] and any("protect private" in x for x in result["limitations"])


@pytest.mark.parametrize("status", ["incomplete", "failed"])
def test_responses_adapter_rejects_noncompleted_status(tmp_path, status):
    captured = []

    class Client:
        def __init__(self, **kwargs):
            self.responses = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(
                model_dump=lambda **k: {
                    "status": status,
                    "output": [],
                    "usage": {"total_tokens": 20},
                }
            )

    settings = Settings(openai_api_key="fixture")
    with pytest.raises(ValueError, match="incomplete"):
        ResponsesProvider(settings, factory=Client).complete(
            [], "instructions", TurnBudget(settings)
        )
    assert captured[0]["store"] is False and captured[0]["text"]["format"]["strict"]
    assert captured[0]["include"] == ["reasoning.encrypted_content"]


def test_supported_prose_survives_failed_re_review_of_targeted_repair(client, isolated_app):
    cid = create_case(client)
    original = answer(kind="practical", text="Keep your payment records.")
    original.claims.append(
        AnswerClaim(
            claim_id="bad",
            task_id="task-1",
            kind="practical",
            text="Unsupported recommendation",
            evidence_ids=original.claims[0].evidence_ids,
        )
    )
    review = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="claim-1",
                support="supported",
                reason="Ordinary preparation",
                requires_public_evidence=False,
            ),
            ClaimVerdict(
                claim_id="bad",
                support="unsupported",
                reason="Needs repair",
                requires_public_evidence=False,
            ),
        ],
        primary_question_answered=True,
        next_action_useful=True,
    )
    repaired = original.model_copy(deep=True)
    repaired.claims[1].text = "Different unsupported recommendation"
    provider = ScriptedProvider(original, review, repaired, TimeoutError())
    install(isolated_app, provider)
    result = post(client, cid, "I paid for a product.")
    content = result.json()["assistant_message"]["content"]
    assert "Keep your payment records" in content
    assert "unsupported recommendation" not in content
    assert len(provider.requests) == 4


def test_rejected_document_claim_prevents_incomplete_clean_artifact(client, isolated_app):
    cid = create_case(client)
    proposed = answer(intent="draft")
    proposed.claims[0].in_document = True
    proposed.claims.append(
        AnswerClaim(
            claim_id="bad",
            task_id="task-1",
            kind="legal",
            text="Unsupported material clause",
            in_document=True,
        )
    )
    install(isolated_app, ScriptedProvider(proposed))
    result = post(client, cid, "I paid for a product.")
    assert result.status_code == 200
    assert client.get(f"/api/conversations/{cid}").json()["drafts"] == []


def test_agent_can_request_approved_safety_before_finishing_answer(client, isolated_app):
    cid = create_case(client)
    call = {"type": "function_call", "call_id": "safety", "name": "emit_safety", "arguments": "{}"}
    message = "A threatening situation needs careful guidance."
    provider = ScriptedProvider(([call], [call], None), answer(message))
    install(isolated_app, provider)
    result = post(client, cid, message, stream=True)
    assert result.text.index("event: safety") < result.text.index("event: result")
    assert json.loads(provider.requests[1][0][-1]["output"])["status"] == "delivered"


def test_estimated_cost_distinguishes_cached_tokens_search_and_actual_billing():
    settings = Settings(
        openai_api_key=None,
        agent_pricing_date="2026-11-07",
        agent_pricing={
            "fixture": {
                "input_per_million": 2,
                "cached_input_per_million": 1,
                "output_per_million": 4,
                "search_per_call": 0.01,
            }
        },
    )
    budget = TurnBudget(settings)
    budget.reserve("fixture", search=True)
    budget.report(
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_details": {"cached_tokens": 40},
        },
        model="fixture",
        search=True,
    )
    snapshot = budget.snapshot()
    assert snapshot["estimated_cost_usd"] == pytest.approx(0.01024)
    assert snapshot["actual_billed_cost_usd"] is None
    budget.report(None, model="fixture")
    assert budget.snapshot()["estimated_cost_usd"] is None
    assert budget.snapshot()["known_estimated_cost_usd"] == pytest.approx(0.01024)


def test_public_pdf_extraction_is_page_bounded_and_explicitly_partial(tmp_path, monkeypatch):
    import io

    from reportlab.pdfgen.canvas import Canvas

    from app.services.web_research import SafeSourceFetcher

    output = io.BytesIO()
    canvas = Canvas(output)
    for page in range(3):
        canvas.drawString(
            30,
            700,
            f"Page {page + 1}: "
            + "A relevant official passage with conditions and exceptions. " * 4,
        )
        canvas.showPage()
    canvas.save()
    monkeypatch.setattr(
        "app.services.web_research.fetch",
        lambda *a, **k: (output.getvalue(), "https://sci.gov.in/test.pdf"),
    )
    settings = Settings(openai_api_key=None, web_max_pdf_pages=1)
    source = SafeSourceFetcher(settings).read({"url": "https://sci.gov.in/test.pdf"}, 2)
    assert source["passages"]
    assert all(p["locator"] == "Page 1" for p in source["passages"])
    assert all("first 1 of 3" in p["limitations"] for p in source["passages"])
