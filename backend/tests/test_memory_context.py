from app.config import Settings
from app.graph.workflow import AssistantGraph
from app.rag.retrieval import HybridRetriever
from app.schemas.models import CaseFact, CaseMemory, FactStatus, IntakeExtraction, Provenance
from app.services.context_builder import ContextBuilder
from app.services.intake import deterministic_extract, is_explicit_confirmation


def test_amount_correction_extracts_new_amount():
    first = deterministic_extract("The phone cost ₹18,000")
    second = deterministic_extract("Actually, it was ₹8,000")
    assert first.proposed_facts[0]["value"] == "18000"
    assert second.proposed_facts[0]["value"] == "8000"
    assert second.contradictions


def test_suggestion_is_not_completed_action():
    assert deterministic_extract("I might send an email").completed_actions == []


def test_completed_action_is_detected():
    assert deterministic_extract("I already sent that email").completed_actions


def test_context_is_bounded_and_keeps_current_correction():
    memory = CaseMemory(
        facts={
            "amount": CaseFact(
                key="amount",
                value="8000",
                status=FactStatus.ALLEGED,
                provenance=[Provenance(source_type="message", source_id="m2")],
            )
        },
        contradictions=[
            {"description": "Amount was first reported as 18000 then corrected to 8000"}
        ],
    )
    recent = [{"id": f"m{i}", "role": "user", "content": "x" * 4000} for i in range(20)]
    context = ContextBuilder(max_chars=5000).build(
        current_message="Actually ₹8,000",
        memory=memory,
        summary="Amount corrected",
        recent_messages=recent,
    )
    assert context["current_message"] == "Actually ₹8,000"
    assert context["confirmed_and_reported_facts"]["amount"]["value"] == "8000"
    assert context["contradictions"]
    assert len(str(context)) < 6000


def test_summary_preserves_contradiction_and_status():
    memory = CaseMemory(
        facts={"date": CaseFact(key="date", value="3 June", status=FactStatus.ALLEGED)},
        contradictions=[{"description": "Invoice says 2 June; user recalls 3 June"}],
    )
    summary = ContextBuilder.rolling_summary(memory)
    assert "user_allegation" in summary
    assert "Invoice says 2 June" in summary


def test_contextual_query_rewrite_preserves_original_and_issue():
    context = {"confirmed_and_reported_facts": {"issue_type": {"value": "refund_not_received"}}}
    rewritten = HybridRetriever.rewrite_query("What should I do next?", context)
    assert "What should I do next?" in rewritten
    assert "refund_not_received" in rewritten
    assert "Consumer Protection Act 2019" in rewritten


def test_contextual_next_question_is_classified_as_options():
    extracted = deterministic_extract("What should I do next?")
    assert extracted.intent == "options"


def test_confirmation_requires_a_direct_unambiguous_phrase():
    assert is_explicit_confirmation("I confirm") is True
    assert is_explicit_confirmation("Yes, but I also sent another email") is False


def test_structured_intake_populates_private_workspace_with_provenance(tmp_path, monkeypatch):
    settings = Settings(
        openai_api_key=None,
        checkpoint_path=tmp_path / "cp.sqlite3",
        chroma_path=tmp_path / "chroma",
    )
    graph = AssistantGraph(settings, HybridRetriever(settings))
    extraction = IntakeExtraction.model_validate(
        {
            "domain": "consumer",
            "proposed_facts": [],
            "parties": [{"name": "Example Shop", "role": "seller"}],
            "locations": [{"value": "Pune", "role": "consumer_location"}],
            "events": [{"date": "2026-10-02", "description": "Refund requested"}],
            "requested_remedy": "refund",
            "completed_actions": ["Sent a refund request"],
            "responses_received": [
                {"from_party": "Example Shop", "date": "2026-10-03", "content": "Refund processed"}
            ],
            "correspondence": [
                {
                    "direction": "sent",
                    "party": "Example Shop",
                    "date": "2026-10-02",
                    "description": "Requested refund",
                }
            ],
            "contradictions": [],
            "urgent_reason": None,
            "needs_legal_retrieval": False,
            "intent": "intake",
            "questions": [],
            "explicit_requests": [
                {
                    "request_id": "request-1",
                    "kind": "case_update",
                    "request_text": "I wrote to Example Shop",
                    "requires_legal_retrieval": False,
                }
            ],
        }
    )
    monkeypatch.setattr(graph.intake, "extract", lambda *_args: (extraction, {}))
    result = graph.extract_and_update(
        {
            "current_message": "I wrote to Example Shop",
            "message_id": "message-1",
            "context": {},
            "memory": CaseMemory().model_dump(mode="json"),
            "events": [],
        }
    )
    memory = CaseMemory.model_validate(result["memory"])
    assert memory.parties[0]["source_id"] == "message-1"
    assert memory.events[0]["description"] == "Refund requested"
    assert memory.requested_remedy == "refund"
    assert memory.requested_remedy_provenance[0].source_id == "message-1"
    assert memory.action_provenance["Sent a refund request"][0].source_id == "message-1"
    assert memory.responses_received[0]["content"] == "Refund processed"
    assert memory.version == 1
    graph.connection.close()
