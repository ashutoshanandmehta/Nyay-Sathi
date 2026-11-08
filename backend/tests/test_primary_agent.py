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


def test_reported_usage_releases_conservative_reservation_for_review():
    settings = Settings(
        openai_api_key=None,
        agent_max_tokens=50_000,
        agent_max_output_tokens=6_000,
    )
    budget = TurnBudget(settings)
    reservation = budget.reserve("fixture", input_chars=30_000)
    assert budget.snapshot()["outstanding_token_reservations"] == 36_000
    budget.report(
        {"input_tokens": 4_000, "output_tokens": 1_000, "total_tokens": 5_000},
        model="fixture",
        reservation=reservation,
    )
    assert budget.snapshot()["outstanding_token_reservations"] == 0
    assert budget.reserve("review", input_chars=30_000) == 36_000


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


def test_extended_timeout_and_multi_turn_police_station_talking_points_continuity(
    client, isolated_app
):
    from app.agent.safety import classify_urgent_context

    defaults = Settings(_env_file=None, openai_api_key=None)
    assert defaults.agent_deadline_seconds == 180
    assert defaults.model_timeout_seconds == 120.0
    assert defaults.agent_repair_min_remaining_seconds == 25.0

    cid = create_case(client)
    msg1 = "Police entered our OYO room in India and demanded a cash bribe immediately."
    segs1 = segment_message(msg1)
    ans1 = answer(msg1, domain="criminal", intent="legal_options")
    ans1.risk = "urgent"

    class MultiTurnProvider:
        def __init__(self):
            self.call = 0

        def complete(self, items, instructions, budget, **kwargs):
            self.call += 1
            budget.reserve("fixture")
            budget.report({"input_tokens": 10, "output_tokens": 10, "total_tokens": 20})
            if self.call == 1:
                return [], [], ans1
            if kwargs.get("review"):
                payload = json.loads(items[0]["content"])
                return (
                    [],
                    [],
                    AgentReview(
                        claims=[
                            ClaimVerdict(
                                claim_id=cid_key,
                                support="supported",
                                reason="Safe non-confrontational talking points grounded in user history",
                                requires_public_evidence=False,
                            )
                            for cid_key in payload["pending_claim_ids"]
                        ],
                        primary_question_answered=True,
                        next_action_useful=True,
                    ),
                )
            ctx = json.loads(items[0]["content"])
            prior_user_ids = [
                e["evidence_id"]
                for e in ctx["evidence"]
                if e["kind"] == "prior_user_message"
            ]
            assert prior_user_ids, "Prior user messages must be registered in context.evidence"
            cur_seg = "segment:" + ctx["segments"][0]["id"]
            return (
                [],
                [],
                AgentAnswer(
                    central_question="Calm police station talking points",
                    tasks=[
                        AgentTask(
                            task_id="task-1",
                            title="Police station talking points",
                            intent="conversation",
                            domain="general",
                            case_link="uncertain",
                            source_segment_ids=[ctx["segments"][0]["id"]],
                        )
                    ],
                    claims=[
                        AnswerClaim(
                            claim_id="tp-1",
                            task_id="task-1",
                            kind="factual",
                            block_type="direct_answer",
                            grounding="reported_by_user",
                            text="State your hotel check-in details and the cash demand you reported earlier without speculating about identity.",
                            evidence_ids=[prior_user_ids[0], cur_seg],
                        ),
                        AnswerClaim(
                            claim_id="tp-2",
                            task_id="task-1",
                            kind="practical",
                            block_type="immediate_actions",
                            grounding="practical_precaution",
                            text="Ask calmly for the Duty Officer or Station House Officer (SHO) and request a written acknowledgement or diary number.",
                            evidence_ids=[],
                        ),
                    ],
                    risk="ordinary",
                ),
            )

    install(isolated_app, MultiTurnProvider())
    r1 = post(client, cid, msg1)
    assert r1.status_code == 200

    r2 = post(client, cid, "After going to the police station, what should I say to them?")
    assert r2.status_code == 200
    body2 = r2.json()["assistant_message"]
    assert "could not verify" not in body2["content"].lower()
    assert "couldn't verify" not in body2["content"].lower()
    assert "Duty Officer" in body2["content"]
    assert body2["metadata"]["publication_status"] == "supported"
    assert body2["metadata"]["interpretation"]["tasks"][0]["case_link"] == "existing"

    short_ctx = classify_urgent_context(
        "what?",
        memory={"domain": "criminal", "facts": {}},
        prior_safety_messages=[{"content_id": "safety-1", "category": "physical_safety"}],
    )
    assert short_ctx["urgent_continuation"] is True


def test_re_review_timeout_preserves_unchanged_patches_and_explicit_practical_precautions(
    client, isolated_app
):
    cid = create_case(client)
    msg = "Police entered our room in Patna and took 2000 cash."
    segs = segment_message(msg)
    seg_ref = f"segment:{segs[0]['id']}"
    original = AgentAnswer(
        central_question="Urgent follow-up steps",
        tasks=[
            AgentTask(
                task_id="task-1",
                title="Urgent steps",
                intent="legal_options",
                domain="criminal",
                case_link="new",
                source_segment_ids=[segs[0]["id"]],
            )
        ],
        claims=[
            AnswerClaim(
                claim_id="bad-1",
                task_id="task-1",
                kind="legal",
                block_type="direct_answer",
                grounding="verified_legal_source",
                text="Unsupported statutory assertion.",
                evidence_ids=[seg_ref],
            )
        ],
        case_patches=[
            CasePatch(
                patch_id="p1",
                task_id="task-1",
                operation="fact",
                payload=PatchValue(key="city", value="Patna"),
                source_refs=[seg_ref],
            )
        ],
        risk="urgent",
    )
    # Put bad-1 into pending by making it practical without public requirement first
    original.claims[0] = AnswerClaim(
        claim_id="bad-1",
        task_id="task-1",
        kind="practical",
        block_type="recommended_route",
        grounding="practical_precaution",
        text="Go confront them outside.",
        evidence_ids=[seg_ref],
    )
    first_review = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="bad-1",
                support="unsupported",
                reason="Unsafe confrontation",
                requires_public_evidence=False,
            )
        ],
        patch_verdicts=[PatchVerdict(patch_id="p1", support="supported", reason="Exact city")],
        primary_question_answered=False,
        next_action_useful=False,
    )
    repaired = original.model_copy(deep=True)
    repaired.claims = [
        AnswerClaim(
            claim_id="safe-precaution",
            task_id="task-1",
            kind="practical",
            block_type="immediate_actions",
            grounding="practical_precaution",
            text="Ask hotel reception to preserve lobby CCTV and visitor logs.",
            evidence_ids=[seg_ref],
        ),
        AnswerClaim(
            claim_id="disguised-law",
            task_id="task-1",
            kind="practical",
            block_type="direct_answer",
            grounding="practical_precaution",
            text="Under Section 7 of the Act, 1988 they must refund within 24 hours by law.",
            evidence_ids=[seg_ref],
        ),
    ]
    provider = ScriptedProvider(original, first_review, repaired, TimeoutError("APITimeoutError"))
    install(isolated_app, provider)
    res = post(client, cid, msg)
    assert res.status_code == 200
    content = res.json()["assistant_message"]["content"]
    assert "preserve lobby CCTV" in content
    assert "Section 7" not in content
    assert res.json()["case_version"] == 1


def test_cross_block_contradiction_triggers_repair_unlocks_conflicting_claim_and_orders_non_urgent_blocks(
    client, isolated_app
):
    cid = create_case(client)
    msg = (
        "I ordered two ceiling fans from Amazon for ₹6,400. One arrived damaged and was picked up "
        "20 days ago, but my ₹3,200 refund hasn't arrived. Can I take legal action?"
    )
    segs = segment_message(msg)
    seg_ref = f"segment:{segs[0]['id']}"

    initial = AgentAnswer(
        central_question="Can I take legal action for my delayed ₹3,200 Amazon refund?",
        tasks=[
            AgentTask(
                task_id="task-1",
                title="Consumer refund strategy",
                intent="legal_options",
                domain="consumer",
                case_link="new",
                source_segment_ids=[segs[0]["id"]],
            )
        ],
        claims=[
            AnswerClaim(
                claim_id="c-direct",
                task_id="task-1",
                kind="factual",
                block_type="direct_answer",
                grounding="reported_by_user",
                text="File immediately in the District Consumer Commission today.",
                evidence_ids=[seg_ref],
            ),
            AnswerClaim(
                claim_id="c-imm",
                task_id="task-1",
                kind="practical",
                block_type="immediate_actions",
                grounding="practical_precaution",
                text="1. Send your Order ID and pickup proof.\n2. Keep your submission timestamp.",
                evidence_ids=[seg_ref],
            ),
            AnswerClaim(
                claim_id="c-route",
                task_id="task-1",
                kind="legal",
                block_type="recommended_route",
                grounding="verified_legal_source",
                text="Escalate first in writing to Amazon's statutory Grievance Officer; under Rule 4, complaints must be acknowledged in 48 hours and redressed within one month.",
                evidence_ids=["prop-consumer-ecommerce-grievance-r4"],
            ),
            AnswerClaim(
                claim_id="c-ev",
                task_id="task-1",
                kind="practical",
                block_type="evidence_checklist",
                grounding="practical_precaution",
                text="Save the invoice, pickup confirmation, and chat transcripts.",
                evidence_ids=[seg_ref],
            ),
        ],
        case_stage="internal_support_attempted",
        next_action="Send written grievance to Amazon's Grievance Officer.",
    )

    # Initial review spots contradiction between c-direct (auto-approved mechanically) and c-route
    first_review = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="c-direct",
                support="uncertain",
                reason="Contradicts recommended_route by telling user to file in court immediately without framing Grievance Officer first.",
                requires_public_evidence=False,
            ),
            ClaimVerdict(
                claim_id="c-route",
                support="supported",
                reason="Entailed by certified E-Commerce Rules proposition.",
                requires_public_evidence=True,
            ),
        ],
        primary_question_answered=True,
        next_action_useful=True,
        cross_block_coherent=False,
        repair_instructions=[
            "Harmonize c-direct with c-route so Direct answer frames Grievance Officer first before formal consumer forum litigation."
        ],
    )

    repaired = initial.model_copy(deep=True)
    repaired.claims[0] = AnswerClaim(
        claim_id="c-direct",
        task_id="task-1",
        kind="legal",
        block_type="direct_answer",
        grounding="verified_legal_source",
        text="Yes — you have statutory consumer remedies up to the District Consumer Commission, starting right now with a formal written complaint to Amazon's Grievance Officer since ordinary support stalled.",
        evidence_ids=["prop-consumer-ecommerce-grievance-r4"],
    )

    second_review = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="c-direct",
                support="supported",
                reason="Coherent with recommended_route and entailed by certified source.",
                requires_public_evidence=True,
            ),
            ClaimVerdict(
                claim_id="c-route",
                support="supported",
                reason="Entailed by certified source.",
                requires_public_evidence=True,
            ),
        ],
        primary_question_answered=True,
        next_action_useful=True,
        cross_block_coherent=True,
    )

    install(isolated_app, ScriptedProvider(initial, first_review, repaired, second_review))
    res = post(client, cid, msg)
    assert res.status_code == 200, res.text
    msg_data = res.json()["assistant_message"]
    blocks = msg_data["metadata"]["resolution_blocks"]
    # Non-urgent consumer order: direct_answer -> recommended_route -> immediate_actions -> evidence_checklist
    assert [b["block_type"] for b in blocks] == [
        "direct_answer",
        "recommended_route",
        "immediate_actions",
        "evidence_checklist",
    ]
    assert "starting right now with a formal written complaint" in blocks[0]["content"]
    # Copy text (message.content) follows the exact same top-to-bottom block order
    content = msg_data["content"]
    assert content.index("starting right now") < content.index("Escalate first in writing")
    assert content.index("Escalate first in writing") < content.index("Send your Order ID")
    assert content.index("Send your Order ID") < content.index("Save the invoice")


def test_multiturn_coverage_marks_prior_sources_and_shows_only_runtime_referral(
    client, isolated_app
):
    cid = create_case(client)
    msg1 = "Police entered our OYO hotel room in India and demanded a cash bribe immediately."
    segs1 = segment_message(msg1)

    ans1 = AgentAnswer(
        central_question="Urgent hotel police harassment",
        tasks=[
            AgentTask(
                task_id="task-1",
                title="Urgent protection",
                intent="legal_options",
                domain="criminal",
                case_link="new",
                source_segment_ids=[segs1[0]["id"]],
            )
        ],
        claims=[
            AnswerClaim(
                claim_id="t1-law",
                task_id="task-1",
                kind="legal",
                block_type="direct_answer",
                grounding="verified_legal_source",
                text="Demanding an undue advantage in connection with public duty falls under Section 7 of the Prevention of Corruption Act.",
                evidence_ids=["prop-urgent-pca-1988-bribe-demand-s7"],
            ),
            AnswerClaim(
                claim_id="t1-ev",
                task_id="task-1",
                kind="practical",
                block_type="evidence_checklist",
                grounding="practical_precaution",
                text="Preserve booking records and ask hotel reception to retain CCTV.",
                evidence_ids=[f"segment:{segs1[0]['id']}"],
            ),
            AnswerClaim(
                claim_id="t1-handoff",
                task_id="task-1",
                kind="practical",
                block_type="human_handoff",
                grounding="practical_precaution",
                text="Consult a lawyer.",
                evidence_ids=[],
                optional=True,
            ),
        ],
        next_action="Prioritize safety and verify dispatch via 112 when safe.",
        risk="urgent",
    )

    rev1 = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="t1-law",
                support="supported",
                reason="Matches certified PCA s.7 proposition",
                requires_public_evidence=True,
            ),
            ClaimVerdict(
                claim_id="t1-ev",
                support="supported",
                reason="Safe evidence checklist",
                requires_public_evidence=False,
            ),
        ],
        primary_question_answered=True,
        next_action_useful=True,
    )

    seen_turn2_ctx = {}

    class TwoTurnInspector:
        def __init__(self):
            self.step = 0

        def complete(self, items, instructions, budget, **kwargs):
            self.step += 1
            budget.reserve("fixture")
            budget.report({"input_tokens": 10, "output_tokens": 10, "total_tokens": 20})
            if self.step == 1:
                return [], [], ans1
            if self.step == 2:
                return [], [], rev1
            if self.step == 3:
                seen_turn2_ctx.update(json.loads(items[0]["content"]))
                cur_seg = "segment:" + seen_turn2_ctx["segments"][0]["id"]
                return (
                    [],
                    [],
                    AgentAnswer(
                        central_question="Patna location update",
                        tasks=[
                            AgentTask(
                                task_id="task-1",
                                title="Patna follow-up",
                                intent="legal_options",
                                domain="criminal",
                                case_link="existing",
                                source_segment_ids=[seen_turn2_ctx["segments"][0]["id"]],
                            )
                        ],
                        claims=[
                            AnswerClaim(
                                claim_id="t2-new",
                                task_id="task-1",
                                kind="factual",
                                block_type="direct_answer",
                                grounding="reported_by_user",
                                text="You report that you are in Patna, Bihar.",
                                evidence_ids=[cur_seg],
                            )
                        ],
                        risk="urgent",
                    ),
                )
            return (
                [],
                [],
                AgentReview(
                    claims=[
                        ClaimVerdict(
                            claim_id="t2-new",
                            support="supported",
                            reason="Exact user report",
                            requires_public_evidence=False,
                        )
                    ],
                    primary_question_answered=True,
                    next_action_useful=True,
                ),
            )

    install(isolated_app, TwoTurnInspector())
    r1 = post(client, cid, msg1)
    assert r1.status_code == 200
    blocks1 = r1.json()["assistant_message"]["metadata"]["resolution_blocks"]
    # The unreviewed model referral never shows; the runtime referral closes the urgent turn.
    handoffs1 = [b for b in blocks1 if b["block_type"] == "human_handoff"]
    assert handoffs1 == [blocks1[-1]] and handoffs1[0]["claim_ids"] == ["runtime-handoff"]

    r2 = post(client, cid, "I think those officers were fake.")
    assert r2.status_code == 200
    cov = seen_turn2_ctx["conversation_context"]["prior_assistant_coverage"]
    assert cov["assistant_turn_count"] == 1
    assert cov["evidence_checklist_already_shown"] is True
    assert "direct_answer" in cov["delivered_block_types"]
    assert cov["covered_source_ids"]
    public_marked = [
        e for e in seen_turn2_ctx["evidence"] if e.get("already_cited_in_prior_turn") is True
    ]
    assert public_marked, "Previously cited certified source should be flagged on Turn 2"
    blocks2 = r2.json()["assistant_message"]["metadata"]["resolution_blocks"]
    handoffs2 = [b for b in blocks2 if b["block_type"] == "human_handoff"]
    assert handoffs2 == [blocks2[-1]] and handoffs2[0]["claim_ids"] == ["runtime-handoff"]


def _certified_fixture(passage_id, locator, text):
    return {
        "passage_id": passage_id,
        "source_id": passage_id + "-src",
        "title": "Synthetic certified fixture " + passage_id,
        "locator": locator,
        "text": text,
        "canonical_url": f"https://www.indiacode.nic.in/{passage_id}.pdf",
        "retrieved_at": "2026-11-07T00:00:00Z",
        "limitations": "",
        "origin": "certified_proposition",
        "source_type": "indian_official",
        "certified_proposition": True,
        "origin_verified": True,
    }


def test_numbered_citations_follow_display_order_and_match_sources(client, isolated_app):
    cid = create_case(client)
    message = "What is an FIR and how is it registered?"
    seg = "segment:" + segment_message(message)[0]["id"]
    fir = _certified_fixture(
        "fix-fir",
        "BNSS 2023, Section 173",
        "Section 173 BNSS: information of a cognizable offence.",
    )
    remedy = _certified_fixture(
        "fix-remedy",
        "BNSS 2023, Section 175",
        "Section 175 BNSS: magistrate may order investigation.",
    )
    research = SimpleNamespace(
        retrieve_certified=lambda query, jurisdiction="India", limit=4, **_: (
            [fir, remedy],
            {"query_hash": "fixture"},
        )
    )
    claims = [
        # Listed first, displayed after the direct answer: numbering must follow display order.
        AnswerClaim(
            claim_id="alt",
            task_id="task-1",
            kind="legal",
            block_type="alternatives",
            grounding="verified_legal_source",
            text="If police refuse, a magistrate can be approached.",
            evidence_ids=["fix-remedy", "fix-fir"],
        ),
        AnswerClaim(
            claim_id="def",
            task_id="task-1",
            kind="legal",
            block_type="direct_answer",
            grounding="verified_legal_source",
            text="An FIR records information about a cognizable offence [7].",
            evidence_ids=["fix-fir"],
        ),
        AnswerClaim(
            claim_id="route",
            task_id="task-1",
            kind="procedure",
            block_type="recommended_route",
            grounding="verified_legal_source",
            text="Give the information orally or in writing.",
            evidence_ids=["fix-fir"],
        ),
        AnswerClaim(
            claim_id="keep",
            task_id="task-1",
            kind="practical",
            block_type="evidence_checklist",
            grounding="practical_precaution",
            text="Keep a copy of what you submit.",
            evidence_ids=[seg, "fix-fir"],
        ),
    ]
    first = AgentAnswer(
        central_question="What is an FIR?",
        tasks=[
            AgentTask(
                task_id="task-1",
                title="FIR",
                intent="information",
                domain="criminal",
                case_link="unrelated",
            )
        ],
        claims=claims,
    )
    review = AgentReview(
        claims=[
            ClaimVerdict(claim_id=c.claim_id, support="supported", reason="fixture") for c in claims
        ],
        primary_question_answered=True,
        next_action_useful=True,
    )
    provider = ScriptedProvider(first, review, answer("Thanks, that helps."))
    install(isolated_app, provider, research)

    data = post(client, cid, message).json()
    content = data["assistant_message"]["content"]
    assert "[Source:" not in content and "[7]" not in content
    assert content.count("[1](#cite-1)") == 3  # direct answer, route, and the alternatives claim
    assert "[1](#cite-1)[2](#cite-2)" in content  # one claim, two sources, ascending
    assert content.index("[1](#cite-1)") < content.index("[2](#cite-2)")
    assert (
        "copy of what you submit." in content and "submit. [" not in content
    )  # checklists unnumbered
    sources = data["assistant_message"]["metadata"]["sources"]
    assert [(s["passage_id"], s["citation_number"]) for s in sources] == [
        ("fix-fir", 1),
        ("fix-remedy", 2),
    ]
    persisted = client.get(f"/api/conversations/{cid}").json()["messages"][-1]["metadata"][
        "sources"
    ]
    assert [s["citation_number"] for s in persisted] == [1, 2]

    assert post(client, cid, "Thanks, that helps.").status_code == 200
    context = json.loads(provider.requests[2][0][0]["content"])
    prior = [
        t["content"]
        for t in context["conversation_context"]["recent_turns"]
        if t["role"] == "assistant"
    ]
    assert prior and all("#cite-" not in text for text in prior)


def test_citation_markers_keep_tables_intact_and_strip_cleanly():
    from app.agent.blocks import append_citation_markers
    from app.answers.evidence import strip_citation_markers

    assert (
        append_citation_markers("Plain claim.", [1, 2]) == "Plain claim. [1](#cite-1)[2](#cite-2)"
    )
    assert append_citation_markers("| Forum | Limit |\n| --- | --- |", [1]).endswith(
        "|\n\n[1](#cite-1)"
    )
    assert append_citation_markers("No sources.", []) == "No sources."
    assert (
        strip_citation_markers("Claim. [1](#cite-1)[2](#cite-2)\n\n[Source: Act — s.1]") == "Claim."
    )
