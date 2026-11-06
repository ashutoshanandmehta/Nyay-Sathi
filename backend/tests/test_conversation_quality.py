from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.graph.workflow import AssistantGraph
from app.rag.retrieval import HybridRetriever
from app.schemas.models import (
    CaseFact,
    CaseMemory,
    FactStatus,
    IntakeExtraction,
    ResponseEnvelope,
    ResponseReview,
)
from app.services.context_builder import ContextBuilder
from app.services.intake import deterministic_extract, is_explicit_confirmation
from app.services.request_coverage import detect_explicit_requests, finalise_response
from app.services.runtime_tools import (
    add_calendar_days,
    calculate_days_between,
    decimal_calculation,
)


def test_versioned_prompts_require_acknowledgement_and_feedback_coverage():
    prompt_root = Path(__file__).parents[1] / "app" / "prompts" / "v1"
    system = (prompt_root / "system.md").read_text()
    review = (prompt_root / "verification.md").read_text()
    assert "before any heading" in system
    assert "every latest explicit request" in review
    assert "desired resolution" in review


REGRESSION_MESSAGE = (
    "I ordered a mixer grinder from HomeStore for ₹3,200. "
    "Delivery was promised by 12 October. Tracking says delivered, but I did not receive it. "
    "No one at home or reception received it. The courier has not shown a delivery photo or OTP record. "
    "What evidence should I collect? Prepare a factual complaint summary."
)


def test_regression_message_tracks_both_explicit_requests():
    requests = detect_explicit_requests(REGRESSION_MESSAGE)
    assert [item.kind for item in requests] == ["evidence_checklist", "factual_summary"]
    assert all(item.requires_legal_retrieval is False for item in requests)


def test_follow_up_request_detection_for_revision_language_and_completed_action():
    assert detect_explicit_requests("Make it shorter.")[0].kind == "revision"
    assert detect_explicit_requests("Explain in Hindi.")[0].kind == "translation"
    assert detect_explicit_requests("I already complained yesterday.")[0].kind == "case_update"
    completed = deterministic_extract("I already complained yesterday.")
    assert completed.completed_actions == ["I already complained yesterday."]
    assert all(item.key != "reported_date" for item in completed.proposed_facts)


def test_natural_confirmation_is_accepted_but_qualified_yes_is_not():
    assert is_explicit_confirmation("Yes, that’s right.")
    assert is_explicit_confirmation("Yes, that's right.")
    assert not is_explicit_confirmation("Yes, but I also complained yesterday.")


def test_context_always_loads_ist_pending_questions_and_private_evidence_search():
    memory = CaseMemory(
        pending_questions=[{"question": "Do you want a refund?", "kind": "follow_up"}]
    )
    context = ContextBuilder().build(
        current_message="The courier delivery photo is missing",
        memory=memory,
        summary="",
        recent_messages=[],
        evidence=[
            {"id": "invoice", "filename": "invoice.txt", "extracted_text": "₹3,200"},
            {
                "id": "courier",
                "filename": "courier.txt",
                "extracted_text": "No delivery photo supplied by courier",
            },
        ],
    )
    assert context["runtime"]["timezone"] == "Asia/Kolkata"
    assert context["runtime"]["current_date"]
    assert context["pending_question_or_stage"][0]["question"] == "Do you want a refund?"
    assert context["relevant_evidence"][0]["id"] == "courier"


def test_safe_arithmetic_is_separate_from_legal_deadline_logic():
    assert decimal_calculation("3200", "subtract", "900") == "2300"
    assert calculate_days_between("2026-10-12", "2026-10-14") == 2
    assert add_calendar_days("2026-10-12", 2) == "2026-10-14"


def test_renderer_never_emits_internal_coverage_fields():
    requests = detect_explicit_requests("What evidence should I collect?")
    envelope = ResponseEnvelope(
        message_markdown="Collect the invoice and tracking history.",
        request_coverage=[{"request_id": "request-1", "status": "answered", "reason": None}],
        follow_up_questions=["Would you prefer a refund or replacement?"],
    )
    rendered, coverage, questions = finalise_response(envelope, requests)
    assert "request_id" not in rendered
    assert "request_coverage" not in rendered
    assert rendered.count("?") == 1
    assert coverage[0].status == "answered"
    assert questions == ["Would you prefer a refund or replacement?"]


def test_confirmation_only_promotes_latest_proposed_fact(tmp_path, monkeypatch):
    settings = Settings(
        openai_api_key=None,
        checkpoint_path=tmp_path / "cp.sqlite3",
        chroma_path=tmp_path / "chroma",
    )
    graph = AssistantGraph(settings, HybridRetriever(settings))
    extraction = IntakeExtraction(
        domain="unknown",
        proposed_facts=[],
        parties=[],
        locations=[],
        events=[],
        requested_remedy=None,
        completed_actions=[],
        responses_received=[],
        correspondence=[],
        contradictions=[],
        urgent_reason=None,
        needs_legal_retrieval=False,
        intent="conversation",
        questions=[],
        explicit_requests=detect_explicit_requests("Yes, that's right."),
    )
    monkeypatch.setattr(graph.intake, "extract", lambda *_args: (extraction, {}))
    memory = CaseMemory(
        facts={
            "amount": CaseFact(key="amount", value="3200", status=FactStatus.ALLEGED),
            "issue_type": CaseFact(
                key="issue_type", value="non_delivery", status=FactStatus.ALLEGED
            ),
        },
        last_proposed_fact_keys=["amount"],
    )
    result = graph.extract_and_update(
        {
            "current_message": "Yes, that's right.",
            "message_id": "message-confirm",
            "context": {},
            "memory": memory.model_dump(mode="json"),
            "events": [],
        }
    )
    updated = CaseMemory.model_validate(result["memory"])
    assert updated.facts["amount"].status == FactStatus.CONFIRMED
    assert updated.facts["issue_type"].status == FactStatus.ALLEGED
    graph.connection.close()


def test_amount_correction_is_scoped_and_marks_new_value_user_confirmed(tmp_path):
    settings = Settings(
        openai_api_key=None,
        checkpoint_path=tmp_path / "cp.sqlite3",
        chroma_path=tmp_path / "chroma",
    )
    graph = AssistantGraph(settings, HybridRetriever(settings))
    memory = CaseMemory(
        facts={"amount": CaseFact(key="amount", value="18000", status=FactStatus.ALLEGED)}
    )
    result = graph.extract_and_update(
        {
            "current_message": "Actually, the amount was ₹2,300.",
            "message_id": "message-correction",
            "context": {},
            "memory": memory.model_dump(mode="json"),
            "events": [],
        }
    )
    updated = CaseMemory.model_validate(result["memory"])
    assert updated.facts["amount"].value == "2300"
    assert updated.facts["amount"].status == FactStatus.CONFIRMED
    assert updated.contradictions[-1]["resolved"] is True
    graph.connection.close()


def test_unresolved_conflict_does_not_overwrite_existing_fact(tmp_path, monkeypatch):
    settings = Settings(
        openai_api_key=None,
        checkpoint_path=tmp_path / "cp.sqlite3",
        chroma_path=tmp_path / "chroma",
    )
    graph = AssistantGraph(settings, HybridRetriever(settings))
    extraction = IntakeExtraction(
        domain="consumer",
        proposed_facts=[
            {"key": "promised_delivery_date", "value": "14 October", "status": "user_allegation"}
        ],
        parties=[],
        locations=[],
        events=[],
        requested_remedy=None,
        completed_actions=[],
        responses_received=[],
        correspondence=[],
        contradictions=["The earlier message says 12 October."],
        urgent_reason=None,
        needs_legal_retrieval=False,
        intent="draft",
        questions=["Which promised-delivery date is correct?"],
        explicit_requests=detect_explicit_requests("Draft a complaint."),
    )
    monkeypatch.setattr(graph.intake, "extract", lambda *_args: (extraction, {}))
    memory = CaseMemory(
        domain="consumer",
        facts={
            "promised_delivery_date": CaseFact(
                key="promised_delivery_date",
                value="12 October",
                status=FactStatus.CONFIRMED,
            )
        },
    )
    result = graph.extract_and_update(
        {
            "current_message": "The invoice instead shows 14 October. Draft a complaint.",
            "message_id": "message-conflict",
            "context": {},
            "memory": memory.model_dump(mode="json"),
            "events": [],
        }
    )
    updated = CaseMemory.model_validate(result["memory"])
    assert updated.facts["promised_delivery_date"].value == "12 October"
    assert updated.contradictions[-1]["new"] == "14 October"
    assert updated.contradictions[-1]["resolved"] is False
    assert "promised_delivery_date" not in updated.last_proposed_fact_keys
    graph.connection.close()


def test_feedback_failure_routes_to_one_revision_then_hard_gate(tmp_path, monkeypatch):
    settings = Settings(
        openai_api_key="labelled-test-key",
        checkpoint_path=tmp_path / "cp.sqlite3",
        chroma_path=tmp_path / "chroma",
        max_model_calls_per_turn=5,
    )
    # Avoid initialising a live embedding client in this labelled mock test.
    settings.openai_api_key = None
    graph = AssistantGraph(settings, HybridRetriever(settings))
    settings.openai_api_key = "labelled-test-key"

    candidate = ResponseEnvelope(
        message_markdown="I can help.",
        request_coverage=[{"request_id": "request-1", "status": "answered", "reason": None}],
        follow_up_questions=[],
    )
    failed_review = ResponseReview(
        passed=False,
        factual_support_passed=True,
        legal_support_passed=True,
        tone_safe=True,
        request_coverage_passed=False,
        confirmation_handling_passed=True,
        findings=[{"code": "missing_summary", "reason": "The factual summary is missing."}],
        revision_instructions=["Add the requested factual summary."],
    )
    revised = ResponseEnvelope(
        message_markdown="Understood.\n\n**Evidence**\n- Invoice\n\n**Factual summary**\nThe user reports non-delivery.",
        request_coverage=[
            {"request_id": "request-1", "status": "answered", "reason": None},
            {"request_id": "request-2", "status": "answered", "reason": None},
        ],
        follow_up_questions=["Would you like a refund or replacement?"],
    )

    class FakeStructured:
        def __init__(self, schema):
            self.schema = schema

        def invoke(self, _messages):
            if self.schema is ResponseEnvelope:
                value = FakeChat.envelopes.pop(0)
            else:
                value = failed_review
            return {"parsed": value, "raw": SimpleNamespace(usage_metadata={"total_tokens": 5})}

    class FakeChat:
        envelopes = [candidate, revised]

        def __init__(self, **_kwargs):
            pass

        def with_structured_output(self, schema, **_kwargs):
            return FakeStructured(schema)

    monkeypatch.setattr("app.graph.workflow.ChatOpenAI", FakeChat)
    requests = detect_explicit_requests(REGRESSION_MESSAGE)
    state = {
        "current_message": REGRESSION_MESSAGE,
        "message_id": "message-1",
        "context": {},
        "memory": CaseMemory().model_dump(mode="json"),
        "shared_guidance": {},
        "intake_questions": [],
        "request_plan": [item.model_dump(mode="json") for item in requests],
        "passages": [],
        "token_usage": {},
        "model_calls": 1,
        "revision_attempts": 0,
        "revision_succeeded": False,
        "events": [],
        "needs_retrieval": False,
    }
    candidate_result = graph.respond(state)
    review_state = {**state, **candidate_result}
    review_result = graph.review_response(review_state)
    revision_state = {**review_state, **review_result}
    assert graph.route_after_review(revision_state) == "revise"
    revision_result = graph.revise_response(revision_state)
    final_state = {**revision_state, **revision_result}
    verified = graph.verify(final_state)
    # Producing a revision is not proof it fixed the independent findings.
    assert verified["verification"]["passed"] is False
    passed_review = failed_review.model_copy(update={"passed": True, "request_coverage_passed": True, "findings": [], "revision_instructions": []})
    final_state["feedback_review"] = passed_review.model_dump(mode="json")
    assert graph.verify(final_state)["verification"]["passed"] is True
    assert "**Evidence**" in final_state["response"]
    assert "**Factual summary**" in final_state["response"]
    assert "request_coverage" not in final_state["response"]
    assert final_state["response"].count("?") == 1
    graph.connection.close()


def test_materially_conflicting_draft_dates_route_to_targeted_revision(tmp_path):
    settings = Settings(
        openai_api_key=None,
        checkpoint_path=tmp_path / "cp.sqlite3",
        chroma_path=tmp_path / "chroma",
        max_model_calls_per_turn=5,
    )
    graph = AssistantGraph(settings, HybridRetriever(settings))
    settings.openai_api_key = "labelled-test-key"
    review = ResponseReview(
        passed=False,
        factual_support_passed=False,
        legal_support_passed=True,
        tone_safe=True,
        request_coverage_passed=True,
        confirmation_handling_passed=False,
        findings=[
            {
                "code": "material_date_conflict",
                "reason": "The draft selected 12 October although case memory also records 14 October.",
            }
        ],
        revision_instructions=[
            "Use a targeted date placeholder and ask which promised-delivery date is correct."
        ],
    )
    state = {
        "feedback_review": review.model_dump(mode="json"),
        "revision_attempts": 0,
        "model_calls": 3,
    }
    assert graph.route_after_review(state) == "revise"
    graph.connection.close()
