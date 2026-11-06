"""Offline v2 contracts. Provider outputs are labelled doubles; network prohibited."""

import copy
import socket
import uuid
from types import SimpleNamespace

import httpx2
import pytest
from openai import APITimeoutError

from app.answers.contracts import CandidateBatch, UnitReviewBatch
from app.answers.evidence import EvidenceRegistry
from app.answers.pipeline import UnitPipeline
from app.answers.verification import digest, review_binding
from app.config import Settings
from app.memory.patches import CasePatch
from app.routing.contracts import RequestInterpretation
from app.routing.interpretation import ContextualInterpreter, conservative_interpretation
from app.routing.segments import resolve_interpretation, segment_message
from app.schemas.models import CaseMemory
from app.services.model_calls import BudgetExhausted, model_calls

from .conftest import create_case
from .test_request_routing import task


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(
        socket.socket, "connect", lambda *a, **k: pytest.fail("Network is forbidden in v2 fixtures")
    )


def state_fixture(text="I returned two fans. Prepare a factual summary.", domain="consumer"):
    refs = [s["id"] for s in segment_message(text)]
    t = task(
        source_text=text,
        intent="summary",
        domain=domain,
        relationship="reported transaction" if domain == "consumer" else "employee–employer",
        case_link="new",
        requires_case_update=True,
    ).model_copy(update={"source_segment_ids": refs})
    interp = RequestInterpretation(
        schema_version="request-v2", tasks=[t], case_relevance="new", clarification_needed=False
    )
    memory = CaseMemory().model_dump(mode="json")
    patch = CasePatch(
        patch_id="p-fact",
        task_id="task-1",
        operation="fact",
        payload={"key": "reported_problem", "value": text},
        source_refs=[f"segment:{refs[0]}"],
    )
    batch = CandidateBatch(
        schema_version="turn-candidates-v2",
        case_patches=[patch],
        units=[
            {
                "unit_id": "u1",
                "task_id": "task-1",
                "claims": [
                    {
                        "claim_id": "c1",
                        "kind": "factual",
                        "text": "You report returning two fans.",
                        "evidence_ids": [f"segment:{refs[0]}"],
                        "depends_on": [],
                    }
                ],
                "unresolved": [],
                "document_title": None,
                "document_claim_ids": [],
            }
        ],
    )
    review = UnitReviewBatch(
        schema_version="review-v2",
        claims=[
            {"claim_id": "c1", "support": "supported", "findings": [], "content_type": "factual"}
        ],
        task_reviews=[
            {"task_id": "task-1", "completion": "answered", "reason": "Synthetic fixture"}
        ],
        findings=[],
        case_updates_supported=False,
        case_update_reason="Legacy batch approval is not used",
        patch_verdicts=[
            {"patch_id": "p-fact", "support": "supported", "reason": "Exact user report"}
        ],
    )
    state = {
        "pipeline_version": "v2",
        "message_id": "m",
        "current_message": text,
        "memory": copy.deepcopy(memory),
        "base_memory": memory,
        "base_summary": "",
        "context": {},
        "language": "en",
        "interpretation": interp.model_dump(mode="json"),
        "case_task_ids": ["task-1"],
        "case_proposal_task_ids": ["task-1"],
        "case_update_allowed": True,
        "candidate_batch": batch.model_dump(mode="json"),
        "unit_review": review.model_dump(mode="json"),
        "passages": [],
        "tool_records": [],
        "model_calls": 0,
        "summary": "",
    }
    bind(state)
    return state


def bind(state):
    state["reviewed_candidate_digest"] = digest(
        CandidateBatch.model_validate(state["candidate_batch"])
    )
    state["reviewed_context_digest"] = review_binding(state)
    state["exposed_evidence_ids"] = list(EvidenceRegistry(state).entries)


def service():
    return UnitPipeline(
        Settings(openai_api_key=None), model_factory=lambda **k: pytest.fail("Real model forbidden")
    )


def test_segments_retain_original_unicode_offsets_and_do_not_invent_text():
    text = "  मैंने ₹८०० दिए।\n\nI might complain tomorrow. " + "word " * 500
    segments = segment_message(text)
    assert len(segments) > 2
    assert all(text[s["start"] : s["end"]] == s["text"] for s in segments)
    assert [s["id"] for s in segments] == [s["id"] for s in segment_message(text)]


def test_one_invalid_task_does_not_destroy_valid_task():
    state = state_fixture()
    base = {k: v for k, v in state["interpretation"]["tasks"][0].items() if k != "source_text"}
    base.update(needs_early_extraction=False, extraction_reason=None)
    invalid = {**base, "task_id": "task-2", "source_segment_ids": ["invented"]}
    result = resolve_interpretation(
        {"tasks": [base, invalid], "clarification_needed": False}, state["current_message"]
    )
    assert len(result.tasks) == 1 and result.invalid_tasks
    assert result.tasks[0].source_text == state["current_message"]


def test_fallback_whatsapp_does_not_create_legal_options_and_consumption_is_sensitive():
    result = conservative_interpretation(
        "My salary is unpaid. I sent a payment request through WhatsApp.", {}
    )
    assert not any(t.intent == "legal_options" for t in result.tasks)
    safety = conservative_interpretation("Is the milk safe to consume?", {}).tasks[0]
    assert safety.domain == "health" and safety.requires_research


def test_practical_checklist_does_not_require_a_legal_citation():
    state = state_fixture()
    state["candidate_batch"]["units"][0]["claims"][0].update(
        kind="preparation", text="Keep the pickup receipt and refund emails together."
    )
    state["unit_review"]["claims"][0]["content_type"] = "practical"
    bind(state)
    result = service().verify_and_compose(state)
    assert "pickup receipt" in result["response"]
    assert result["assistance_status"] == "delivered"


def test_legal_instruction_disguised_as_practical_still_needs_sources():
    state = state_fixture()
    state["candidate_batch"]["units"][0]["claims"][0].update(
        kind="preparation", text="You are entitled to compensation."
    )
    state["unit_review"]["claims"][0]["content_type"] = "legal_conclusion"
    bind(state)
    assert "entitled to compensation" not in service().verify_and_compose(state)["response"]


def test_missing_details_do_not_make_a_delivered_draft_partial():
    state = state_fixture()
    unit = state["candidate_batch"]["units"][0]
    unit.update(unresolved=["Order ID not supplied"], document_claim_ids=["c1"])
    unit["claims"][0].update(
        kind="draft",
        text="Order [ID]: I requested return of two fans. Please review the outstanding refund.",
    )
    bind(state)
    result = service().verify_and_compose(state)
    assert result["assistance_status"] == "delivered"
    assert result["document_status"] == "needs_user_details"


def test_supported_fact_commits_while_unverified_role_stays_staged():
    state = state_fixture()
    state["candidate_batch"]["case_patches"].append(
        {
            "patch_id": "party",
            "task_id": "task-1",
            "operation": "party",
            "payload": {"name": "Amazon", "role": "verified seller"},
            "source_refs": ["segment:seg-1"],
            "depends_on": [],
        }
    )
    state["unit_review"]["patch_verdicts"].append(
        {"patch_id": "party", "support": "uncertain", "reason": "Contracting seller unknown"}
    )
    bind(state)
    result = service().verify_and_compose(state)
    assert result["memory"]["facts"]["reported_problem"]["status"] == "user_allegation"
    assert result["memory"]["version"] == 1
    assert result["memory"]["parties"] == [] and len(result["staged_patches"]) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "unrelated",
        "uncertain",
        "general",
        "unknown_source",
        "unreviewed",
        "outside_segment",
        "cycle",
    ],
)
def test_patch_approval_is_not_authorization(failure):
    state = state_fixture()
    patch = state["candidate_batch"]["case_patches"][0]
    if failure in {"unrelated", "uncertain"}:
        state["interpretation"]["tasks"][0]["case_link"] = failure
    elif failure == "general":
        state["interpretation"]["tasks"][0]["domain"] = "general"
    elif failure == "unknown_source":
        patch["source_refs"] = ["foreign-owner-document"]
    elif failure == "unreviewed":
        state["unit_review"]["patch_verdicts"] = []
    elif failure == "outside_segment":
        patch["source_refs"] = ["message:m"]
    else:
        patch["depends_on"] = [patch["patch_id"]]
    bind(state)
    result = service().verify_and_compose(state)
    assert result["memory"]["facts"] == {} and result["staged_patches"]


def test_generated_save_claim_is_withheld_before_commit():
    state = state_fixture()
    state["candidate_batch"]["units"][0]["claims"][0]["text"] = "I have updated your case."
    bind(state)
    assert "updated your case" not in service().verify_and_compose(state)["response"]


def test_accounting_timeout_is_an_attempt_with_unknown_usage(monkeypatch):
    def handler(request):
        raise httpx2.ReadTimeout("Synthetic timeout", request=request)

    monkeypatch.setattr(
        "app.services.model_calls.DefaultHttpx2Client",
        lambda **k: httpx2.Client(transport=httpx2.MockTransport(handler), **k),
    )
    with model_calls.scope(1) as scope:
        with pytest.raises(APITimeoutError):
            with model_calls.sdk(
                Settings(openai_api_key="fixture"), "generation", "fixture-model"
            ) as client:
                client.responses.create(model="fixture-model", input="synthetic")
    event = scope.records[0]
    assert event["attempts_observed"] == 1 and event["attempts_confirmed"] == 0
    assert event["usage_reported"] is None and event["usage_completeness"] == "unknown"


def test_accounting_retains_usage_before_invalid_interpretation(monkeypatch):
    def handler(request):
        return httpx2.Response(
            200,
            headers={"x-request-id": "fixture-request"},
            json={"usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}},
        )

    monkeypatch.setattr(
        "app.services.model_calls.DefaultHttpx2Client",
        lambda **k: httpx2.Client(transport=httpx2.MockTransport(handler), **k),
    )

    class Fake:
        def __init__(self, **kwargs):
            self.client = kwargs["http_client"]

        def with_structured_output(self, *a, **k):
            return self

        def invoke(self, messages):
            self.client.post("https://example.org/v1/chat/completions", json={})
            return {
                "parsed": {
                    "schema_version": "request-v2",
                    "tasks": [],
                    "clarification_needed": False,
                },
                "raw": None,
            }

    with model_calls.scope(1) as scope:
        with pytest.raises(ValueError):
            ContextualInterpreter(Settings(openai_api_key="fixture"), Fake).interpret(
                "Synthetic", {}
            )
    event = scope.records[0]
    assert (
        event["usage_reported"]["total_tokens"] == 10 and event["usage_completeness"] == "complete"
    )
    assert event["attempts_confirmed"] == 1 and event["first_token_ms"] is None


def test_budget_reservation_blocks_before_provider_transmission():
    with model_calls.scope(0) as scope:
        with pytest.raises(BudgetExhausted):
            with model_calls.sdk(Settings(openai_api_key="fixture"), "generation", "fixture"):
                pytest.fail("Must not construct a provider request")
    assert scope.records == []


def configure_http_fixture(app, monkeypatch):
    graph = app.state.assistant_graph
    graph.settings.openai_api_key = "labelled-offline-fixture"
    fixture = state_fixture()
    parsed = RequestInterpretation.model_validate(fixture["interpretation"])
    graph.interpreter = SimpleNamespace(interpret=lambda *a: (parsed, {}, "synthetic_fixture"))
    monkeypatch.setattr(
        graph.intake, "extract", lambda *a, **k: pytest.fail("Ordinary v2 must not invoke intake")
    )
    calls = []

    def model(schema, review=False):
        def invoke(messages):
            calls.append(schema.__name__)
            return {
                "parsed": CandidateBatch.model_validate(fixture["candidate_batch"])
                if schema is CandidateBatch
                else UnitReviewBatch.model_validate(fixture["unit_review"]),
                "raw": None,
            }

        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(graph.unit_pipeline, "model", model)
    return fixture, calls


def test_http_three_call_path_persists_and_idempotency_rejects_changed_payload(
    client, isolated_app, monkeypatch
):
    fixture, calls = configure_http_fixture(isolated_app, monkeypatch)
    cid = create_case(client)
    body = {"content": fixture["current_message"], "request_id": str(uuid.uuid4())}
    first = client.post(f"/api/conversations/{cid}/turns", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["assistant_message"]["metadata"]["commit_receipt"]["status"] == "committed"
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["case_memory"]["version"] == 1 and detail["case_memory"]["facts"]
    assert first.json() == client.post(f"/api/conversations/{cid}/turns", json=body).json()
    assert calls == ["CandidateBatch", "UnitReviewBatch"]
    assert (
        client.post(
            f"/api/conversations/{cid}/turns", json={**body, "content": "Different message"}
        ).status_code
        == 409
    )


def test_retry_after_commit_finalizes_without_reapplying_or_regenerating(
    client, isolated_app, monkeypatch
):
    fixture, calls = configure_http_fixture(isolated_app, monkeypatch)
    cid = create_case(client)
    body = {"content": fixture["current_message"], "request_id": str(uuid.uuid4())}
    db = isolated_app.state.db
    original = db.add_message

    def fail(cid, role, *a, **k):
        if role == "assistant":
            raise RuntimeError("Synthetic delivery failure")
        return original(cid, role, *a, **k)

    monkeypatch.setattr(db, "add_message", fail)
    with pytest.raises(RuntimeError):
        client.post(f"/api/conversations/{cid}/turns", json=body)
    assert client.get(f"/api/conversations/{cid}").json()["case_memory"]["version"] == 1
    monkeypatch.setattr(db, "add_message", original)
    response = client.post(f"/api/conversations/{cid}/turns", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["case_version"] == 1 and calls == ["CandidateBatch", "UnitReviewBatch"]
    assert len(client.get(f"/api/conversations/{cid}").json()["messages"]) == 2


def test_preservation_of_nch_receipt_is_not_a_filing_instruction():
    state = state_fixture()
    state["candidate_batch"]["units"][0]["claims"][0].update(
        kind="preparation", text="Keep your NCH complaint receipt with the refund correspondence."
    )
    state["unit_review"]["claims"][0]["content_type"] = "practical"
    bind(state)
    assert "Keep your NCH" in service().verify_and_compose(state)["response"]


def test_suggestion_is_not_a_completed_action_even_with_erroneous_reviewer_support():
    state = state_fixture("I might complain tomorrow. Prepare a summary.")
    state["candidate_batch"]["case_patches"][0].update(
        operation="action", payload={"description": "Complaint filed"}
    )
    bind(state)
    result = service().verify_and_compose(state)
    assert result["memory"]["actions_completed"] == [] and result["staged_patches"]


def test_stage_aware_read_only_plan_does_not_restart_exhausted_support(isolated_app):
    graph = isolated_app.state.assistant_graph
    story = "I ordered three fans from Amazon. I contacted support repeatedly. Support promised the remaining refund but closed the investigation. I also emailed the grievance team, who redirected me to regular support. Suggest the next practical step."
    state = state_fixture(story)
    state["interpretation"]["tasks"][0].update(intent="legal_options", requires_research=True)
    before = copy.deepcopy(state["memory"])
    result = graph.plan_resolution(state)
    assert result["resolution_plan"]["recommended_route_id"] == "nch"
    assert not {"support", "grievance"} & {
        r["route_id"] for r in result["resolution_plan"]["alternatives"]
    }
    assert result["memory"] == before and result["draft_spec"] == {}
    nch = next(r for r in result["resolution_plan"]["alternatives"] if r["route_id"] == "nch")
    assert nch["source_urls"] and nch["eligibility"]["status"] == "insufficient_information"


def test_a_hypothetical_grievance_is_not_reported_as_exhausted():
    from app.resolution.planner import ResolutionPlanner

    memory = CaseMemory(domain="consumer")
    plan = ResolutionPlanner().recommend(
        memory, "I ordered from Amazon. If I emailed the grievance team would they help?"
    )
    assert plan.recommended_route_id == "support"


def test_stale_cache_does_not_establish_freshness():
    from app.routing.task_context import ApplicabilityPolicy

    assert not ApplicabilityPolicy.cache_recent({"retrieved_at": "2020-01-01"})
    assert not ApplicabilityPolicy.cache_recent({"retrieved_at": "not-a-date"})
    assert not ApplicabilityPolicy.cache_recent(
        {"retrieved_at": "2026-11-07", "verification_status": "conflicting"}
    )


def owner_of(db, cid):
    with db.connect() as conn:
        return conn.execute("SELECT owner_id FROM conversations WHERE id=?", (cid,)).fetchone()[0]


def test_database_execution_claim_excludes_other_requests_and_owners(client, isolated_app):
    from app.services.turn_persistence import RequestConflict, TurnPersistence

    cid = create_case(client)
    db = isolated_app.state.db
    owner = owner_of(db, cid)
    store = TurnPersistence(db)
    store.begin(owner, cid, "first", "a")
    with pytest.raises(RequestConflict):
        store.begin(owner, cid, "second", "b")
    with pytest.raises(RequestConflict):
        store.begin(owner, cid, "first", "a")
    with pytest.raises(KeyError):
        store.get("foreign-owner", cid, "first")
    with pytest.raises(KeyError):
        db.model_call_events("foreign-owner", cid, "first")


def test_dead_worker_request_can_resume_without_fabricating_review(client, isolated_app):
    import json

    from app.services.turn_persistence import TurnPersistence

    cid = create_case(client)
    db = isolated_app.state.db
    owner = owner_of(db, cid)
    store = TurnPersistence(db)
    store.begin(owner, cid, "interrupted", "a")
    with db.connect() as conn:
        conn.execute(
            "UPDATE turn_executions SET verified_json=? WHERE conversation_id=?",
            (json.dumps({"worker_pid": 999999999}), cid),
        )
    assert store.begin(owner, cid, "interrupted", "a")["status"] == "running"
    assert store.get(owner, cid, "interrupted")["receipt_json"] is None


def test_case_conflict_rolls_back_patch_audit_and_preserves_user_edited_draft(
    client, isolated_app, monkeypatch
):
    from app.db import MemoryConflict
    from app.routing.state_manager import CaseStateManager

    fixture, calls = configure_http_fixture(isolated_app, monkeypatch)
    cid = create_case(client)
    db = isolated_app.state.db
    owner = owner_of(db, cid)
    draft = db.create_draft(owner, cid, "My own letter", "User-edited correspondence", 0)
    original = CaseStateManager.commit

    def conflict(*a, **k):
        raise MemoryConflict("Synthetic concurrent edit")

    monkeypatch.setattr(CaseStateManager, "commit", conflict)
    body = {"content": fixture["current_message"], "request_id": str(uuid.uuid4())}
    response = client.post(f"/api/conversations/{cid}/turns", json=body)
    assert response.status_code == 409
    monkeypatch.setattr(CaseStateManager, "commit", original)
    assert client.post(f"/api/conversations/{cid}/turns", json=body).status_code == 409
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["case_memory"]["version"] == 0 and not detail["case_memory"]["facts"]
    assert (
        detail["drafts"][0]["id"] == draft["id"]
        and detail["drafts"][0]["content"] == "User-edited correspondence"
    )
    assert calls == ["CandidateBatch", "UnitReviewBatch"]
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM case_patch_audit WHERE conversation_id=?", (cid,)
            ).fetchone()[0]
            == 0
        )


def test_delete_cascades_new_receipts_telemetry_and_patch_records(
    client, isolated_app, monkeypatch
):
    fixture, _ = configure_http_fixture(isolated_app, monkeypatch)
    cid = create_case(client)
    req = str(uuid.uuid4())
    assert (
        client.post(
            f"/api/conversations/{cid}/turns",
            json={"content": fixture["current_message"], "request_id": req},
        ).status_code
        == 200
    )
    db = isolated_app.state.db
    db.record_model_call(
        owner_of(db, cid), cid, req, {"call_id": "synthetic", "usage_completeness": "unknown"}
    )
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    with db.connect() as conn:
        for table in ("turn_executions", "case_patch_audit", "model_call_events", "turn_artifacts"):
            assert (
                conn.execute(
                    f"SELECT count(*) FROM {table} WHERE conversation_id=?", (cid,)
                ).fetchone()[0]
                == 0
            )


def test_token_subsets_are_not_double_counted():
    from app.services.model_calls import normalize_usage

    report = normalize_usage(
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 80},
            "output_token_details": {"reasoning": 15},
        }
    )
    assert report["total_tokens"] == 120 and report["input_details"]["cache_read"] == 80
    assert report["output_details"]["reasoning"] == 15


def test_partial_success_preserves_draft_when_safety_research_fails():
    state = state_fixture(
        "The delivered milk smells bad. Prepare a complaint and check whether it is safe."
    )
    draft = state["candidate_batch"]["units"][0]
    draft["claims"][0].update(
        kind="draft",
        text="The milk delivered to me smells bad. Please investigate and advise on a refund or replacement.",
    )
    draft["document_claim_ids"] = ["c1"]
    state["interpretation"]["tasks"][0]["intent"] = "draft"
    safety = copy.deepcopy(state["interpretation"]["tasks"][0])
    safety.update(
        task_id="task-2",
        intent="information",
        domain="health",
        case_link="unrelated",
        requires_case_update=False,
        requires_research=True,
    )
    state["interpretation"]["tasks"].append(safety)
    state["candidate_batch"]["units"].append(
        {
            "unit_id": "u2",
            "task_id": "task-2",
            "claims": [
                {
                    "claim_id": "unsafe",
                    "kind": "safety",
                    "text": "This milk is definitely safe to drink.",
                    "evidence_ids": [],
                    "depends_on": [],
                }
            ],
            "unresolved": [],
            "document_title": None,
            "document_claim_ids": [],
        }
    )
    state["unit_review"]["claims"].append(
        {"claim_id": "unsafe", "support": "unsupported", "findings": [], "content_type": "safety"}
    )
    state["unit_review"]["task_reviews"].append(
        {"task_id": "task-2", "completion": "deferred", "reason": "No supporting source"}
    )
    bind(state)
    result = service().verify_and_compose(state)
    assert "milk delivered to me smells bad" in result["response"]
    assert "definitely safe" not in result["response"]
    assert len(result["approved_documents"]) == 1 and result["publication_status"] == "partial"


def test_reported_grievance_survives_follow_up_planning_without_new_writes():
    from app.resolution.planner import ResolutionPlanner
    from app.schemas.models import CaseFact, Provenance

    memory = CaseMemory(
        domain="consumer",
        facts={
            "history": CaseFact(
                key="history",
                value="I ordered fans from Amazon. I emailed the grievance team, who sent me back to support.",
                provenance=[Provenance(source_type="message", source_id="earlier")],
            )
        },
    )
    assert (
        ResolutionPlanner().recommend(memory, "What should I do next?").recommended_route_id
        == "nch"
    )
    assert memory.journey.events == []


def test_reviewed_timeline_event_appends_to_existing_journey():
    state = state_fixture("I emailed Amazon grievance support. Prepare a summary.")
    state["candidate_batch"]["case_patches"][0].update(
        operation="event",
        payload={
            "description": "I emailed Amazon grievance support.",
            "event_type": "complaint_submitted",
            "recipient": "company_grievance",
        },
    )
    bind(state)
    result = service().verify_and_compose(state)
    assert result["memory"]["journey"]["events"][0]["source_id"] == "m"
    assert result["memory"]["journey"]["submissions"][0]["recipient"] == "company_grievance"


def test_v2_correction_keeps_previous_value_and_invalidates_stored_draft(
    client, isolated_app, monkeypatch
):
    from app.schemas.models import CaseFact, Provenance

    fixture, calls = configure_http_fixture(isolated_app, monkeypatch)
    cid = create_case(client)
    db = isolated_app.state.db
    owner = owner_of(db, cid)
    memory = CaseMemory(
        domain="consumer",
        version=1,
        facts={
            "reported_problem": CaseFact(
                key="reported_problem",
                value="Original amount ₹18,000",
                provenance=[Provenance(source_type="message", source_id="old")],
            )
        },
    )
    db.save_memory(cid, memory, "Original report", {}, expected_version=0, owner_id=owner)
    draft = db.create_draft(owner, cid, "Existing letter", "I paid ₹18,000.", 1)
    fixture["current_message"] = "Actually, the amount was ₹8,000."
    fixture["interpretation"]["tasks"][0].update(case_link="existing")
    fixture["candidate_batch"]["case_patches"][0].update(
        operation="correction",
        payload={"key": "reported_problem", "value": "Corrected amount ₹8,000"},
    )
    parsed = RequestInterpretation.model_validate(fixture["interpretation"])
    isolated_app.state.assistant_graph.interpreter = SimpleNamespace(
        interpret=lambda *a: (parsed, {}, "synthetic_fixture")
    )
    response = client.post(
        f"/api/conversations/{cid}/turns",
        json={"content": fixture["current_message"], "request_id": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/conversations/{cid}").json()
    fact = detail["case_memory"]["facts"]["reported_problem"]
    assert (
        fact["value"] == "Corrected amount ₹8,000"
        and fact["previous_values"][0]["value"] == "Original amount ₹18,000"
    )
    assert detail["drafts"][0]["id"] == draft["id"] and detail["drafts"][0]["status"] == "stale"


def test_ordinary_path_batches_extraction_but_complex_path_reserves_review(
    isolated_app, monkeypatch
):
    graph = isolated_app.state.assistant_graph
    state = state_fixture()
    state.update(model_calls=1)
    graph.settings.max_model_calls_per_turn = 4
    monkeypatch.setattr(
        graph.intake,
        "extract",
        lambda *a: (
            SimpleNamespace(model_dump=lambda **k: {"proposed_facts": []}),
            {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
        ),
    )
    assert graph.prepare_v2(state)["model_calls"] == 1
    state["interpretation"]["tasks"][0].update(needs_early_extraction=True)
    complex_result = graph.prepare_v2(state)
    assert (
        complex_result["model_calls"] == 2
        and complex_result["extraction_status"] == "read_only_semantic_extraction"
    )
    graph.settings.max_model_calls_per_turn = 3
    assert graph.prepare_v2(state)["extraction_status"] == "required_extraction_budget_exhausted"


def test_employment_brief_keeps_historical_uncertainty_without_consumer_plan(isolated_app):
    state = state_fixture(
        "My employer owes salary as of March 2026. I do not know which entity employed me. Prepare a factual lawyer brief.",
        domain="employment",
    )
    claim = state["candidate_batch"]["units"][0]["claims"][0]
    claim.update(
        text="You report unpaid salary as of March 2026. The employing legal entity remains uncertain."
    )
    state["candidate_batch"]["units"][0]["document_claim_ids"] = ["c1"]
    bind(state)
    result = service().verify_and_compose(state)
    assert "March 2026" in result["response"] and "remains uncertain" in result["response"]
    assert result["approved_documents"][0]["title"] == "Factual summary"
    assert isolated_app.state.assistant_graph.plan_resolution(state) == {
        "resolution_plan": {},
        "draft_spec": {},
    }


def test_hindi_language_change_does_not_authorize_case_mutation():
    state = state_fixture("इसे हिंदी में समझाइए।")
    state["interpretation"]["tasks"][0].update(
        intent="information", case_link="unrelated", requires_case_update=False
    )
    state["language"] = "hi"
    bind(state)
    result = service().verify_and_compose(state)
    assert result["memory"] == state["base_memory"] and not result["patch_decisions"]
