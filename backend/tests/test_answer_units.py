"""Synthetic candidates/reviewer doubles. No model or search provider calls."""

import copy
import json
import socket
import uuid
from types import SimpleNamespace

import pytest

from app.answers.contracts import CandidateBatch, UnitReviewBatch
from app.answers.pipeline import UnitPipeline
from app.answers.verification import digest, review_binding
from app.config import Settings
from app.db import MemoryConflict
from app.rag.discover import parse_source_candidates
from app.rag.retrieval import HybridRetriever
from app.routing.policy import WorkflowPolicy
from app.routing.task_context import TaskContext
from app.schemas.models import CaseMemory
from app.services.web_research import OfficialSearchProvider

from .conftest import create_case
from .test_request_routing import interpretation, task


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network is forbidden in synthetic answer-unit tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)


def mixed_fixture():
    """A reconstructed regression, not an original live model candidate."""
    text = "The milk delivered by Blinkit smells bad. Is it safe? Draft a refund request."
    tasks = interpretation(
        task(source_text=text, domain="health", requires_research=True),
        task(
            task_id="task-2",
            source_text=text,
            intent="draft",
            domain="consumer",
            case_link="new",
            relationship="buyer and seller",
            requires_case_update=False,
        ),
    )
    batch = CandidateBatch.model_validate(
        {
            "units": [
                {
                    "unit_id": "safety",
                    "task_id": "task-1",
                    "claims": [
                        {
                            "claim_id": "unsafe",
                            "kind": "safety",
                            "text": "This milk is safe to drink.",
                            "evidence_ids": [],
                            "depends_on": [],
                        }
                    ],
                    "unresolved": [],
                    "document_title": None,
                    "document_claim_ids": [],
                },
                {
                    "unit_id": "letter",
                    "task_id": "task-2",
                    "claims": [
                        {
                            "claim_id": "letter",
                            "kind": "draft",
                            "text": "The milk delivered to me smells bad. Please arrange a refund. Order reference: [Order ID].",
                            "evidence_ids": ["message:m"],
                            "depends_on": [],
                        }
                    ],
                    "unresolved": [],
                    "document_title": "Unreviewed title must never be published",
                    "document_claim_ids": ["letter"],
                },
            ]
        }
    )
    review = {
        "claims": [
            {
                "claim_id": "unsafe",
                "support": "unsupported",
                "findings": [
                    {
                        "code": "unsafe_verdict",
                        "severity": "major",
                        "reason": "No reliable safety evidence",
                    }
                ],
            },
            {"claim_id": "letter", "support": "supported", "findings": []},
        ],
        "findings": [],
        "case_updates_supported": False,
        "case_update_reason": "Keep proposals staged",
    }
    memory = CaseMemory().model_dump(mode="json")
    state = {
        "message_id": "m",
        "current_message": text,
        "interpretation": tasks.model_dump(mode="json"),
        "candidate_batch": batch.model_dump(mode="json"),
        "unit_review": review,
        "reviewed_candidate_digest": digest(batch),
        "memory": memory,
        "base_memory": copy.deepcopy(memory),
        "context": {},
        "model_calls": 0,
        "passages": [],
        "case_update_allowed": False,
        "exposed_evidence_ids": ["message:m"],
        "tool_records": [],
        "language": "en",
    }
    state["unit_review"]["task_reviews"] = [
        {"task_id": "task-1", "completion": "deferred", "reason": "Missing safety evidence"},
        {"task_id": "task-2", "completion": "answered", "reason": "Factual letter prepared"},
    ]
    state["reviewed_context_digest"] = review_binding(state)
    return state


def pipeline():
    def forbidden(**kwargs):
        raise AssertionError("A real model must never be constructed by this offline fixture")

    return UnitPipeline(Settings(openai_api_key=None), model_factory=forbidden)


def approve_all(state, findings=None):
    batch = CandidateBatch.model_validate(state["candidate_batch"])
    state["unit_review"] = {
        "claims": [
            {"claim_id": c.claim_id, "support": "supported", "findings": findings or []}
            for u in batch.units
            for c in u.claims
        ],
        "findings": [],
        "case_updates_supported": False,
        "case_update_reason": "No commit",
    }
    state["reviewed_candidate_digest"] = digest(batch)
    state["unit_review"]["task_reviews"] = [
        {
            "task_id": t["task_id"],
            "completion": "answered",
            "reason": "Synthetic task-coverage verdict",
        }
        for t in state["interpretation"]["tasks"]
    ]
    state["reviewed_context_digest"] = review_binding(state)


def public_fixture():
    state = mixed_fixture()
    state["interpretation"] = interpretation(
        task(domain="consumer", intent="information")
    ).model_dump(mode="json")
    state["passages"] = [
        {
            "passage_id": "p1",
            "source_id": "s1",
            "title": "Canonical official title",
            "locator": "Section X",
            "text": "Synthetic fixture about complaint reception; NOT live law.",
            "source_type": "guidance",
            "jurisdiction": "IN",
            "verification_status": "verified_official",
            "effective_date": None,
        }
    ]
    state["candidate_batch"]["units"] = [
        {
            "unit_id": "u1",
            "task_id": "task-1",
            "claims": [
                {
                    "claim_id": "c1",
                    "kind": "legal",
                    "text": "The synthetic office receives complaints. [Source: Wrong model title]",
                    "evidence_ids": ["p1"],
                    "depends_on": [],
                }
            ],
            "document_title": None,
            "document_claim_ids": [],
            "unresolved": [],
        }
    ]
    state["exposed_evidence_ids"] = ["p1", "message:m"]
    approve_all(state)
    return state


def test_partial_success_preserves_draft_and_excludes_unsafe_claim():
    result = pipeline().verify_and_compose(mixed_fixture())
    assert "Please arrange a refund" in result["response"]
    assert "safe to drink" not in result["response"]
    assert result["publication_status"] == "partial"
    assert result["verification"]["publication_safe"]
    assert result["approved_documents"][0]["title"] == "Prepared correspondence"
    assert "Unreviewed title" not in str(result)


def test_canonical_identity_resolves_without_model_display_strings():
    result = pipeline().verify_and_compose(public_fixture())
    assert "Canonical official title — Section X" in result["response"]
    assert "Wrong model title" not in result["response"]
    assert result["published_passage_ids"] == ["p1"]


def test_correct_id_wrong_meaning_is_not_approved():
    state = public_fixture()
    state["unit_review"]["claims"][0]["support"] = "unsupported"
    assert pipeline().verify_and_compose(state)["published_passage_ids"] == []


@pytest.mark.parametrize(
    "severity,visible",
    [
        ("critical", False),
        ("major", False),
        ("moderate", False),
        ("minor", True),
        ("advisory", True),
    ],
)
def test_severity_is_not_a_blanket_style_gate(severity, visible):
    state = public_fixture()
    approve_all(state, [{"code": "fixture", "severity": severity, "reason": "Synthetic finding"}])
    result = pipeline().verify_and_compose(state)
    assert ("synthetic office" in result["response"]) == visible


@pytest.mark.parametrize(
    "failure",
    [
        "unknown_id",
        "not_exposed",
        "wrong_domain",
        "unverified_origin",
        "changed_after_review",
        "duplicate_review",
        "missing_review",
        "unknown_task",
    ],
)
def test_evidence_and_review_faults_fail_closed(failure):
    state = public_fixture()
    claim = state["candidate_batch"]["units"][0]["claims"][0]
    if failure == "unknown_id":
        claim["evidence_ids"] = ["invented"]
        approve_all(state)
    elif failure == "not_exposed":
        state["exposed_evidence_ids"] = ["message:m"]
    elif failure == "wrong_domain":
        state["interpretation"]["tasks"][0]["domain"] = "employment"
    elif failure == "unverified_origin":
        state["passages"][0]["verification_status"] = "unverified_public_source"
    elif failure == "changed_after_review":
        claim["text"] += " Everyone wins."
    elif failure == "duplicate_review":
        state["unit_review"]["claims"] *= 2
    elif failure == "missing_review":
        state["unit_review"] = {}
    else:
        state["candidate_batch"]["units"][0]["task_id"] = "task-8"
        approve_all(state)
    assert pipeline().verify_and_compose(state)["published_passage_ids"] == []


@pytest.mark.parametrize("dependencies", [["unsafe"], ["missing"], ["letter"]])
def test_missing_blocked_or_cyclic_dependencies_do_not_publish(dependencies):
    state = mixed_fixture()
    state["candidate_batch"]["units"][1]["claims"][0]["depends_on"] = dependencies
    approve_all(state)
    assert pipeline().verify_and_compose(state)["approved_documents"] == []


def test_task_coverage_and_status_are_runtime_owned():
    state = mixed_fixture()
    state["candidate_batch"]["units"] = state["candidate_batch"]["units"][1:]
    approve_all(state)
    result = pipeline().verify_and_compose(state)
    assert {u["task_id"] for u in result["unit_outcomes"]} == {"task-1", "task-2"}
    assert {u["task_id"]: u["status"] for u in result["unit_outcomes"]} == {
        "task-2": "supported",
        "task-1": "deferred",
    }


def test_supported_sentences_do_not_imply_task_completion():
    state = public_fixture()
    state["unit_review"]["task_reviews"][0]["completion"] = "partial"
    result = pipeline().verify_and_compose(state)
    assert result["publication_status"] == "partial"
    assert result["request_coverage"][0]["status"] == "deferred"
    assert "synthetic office" in result["response"]


def test_precise_reviewed_limitation_is_visible_without_claiming_answered():
    state = public_fixture()
    state["candidate_batch"]["units"][0]["claims"][0].update(
        kind="limitation",
        text="I could not verify this office's current filing requirements.",
        evidence_ids=[],
    )
    approve_all(state)
    result = pipeline().verify_and_compose(state)
    assert "current filing requirements" in result["response"]
    assert result["publication_status"] == "deferred"


def test_material_conflicting_dates_block_letter_but_preserve_checklist():
    state = mixed_fixture()
    state["candidate_batch"]["units"][0]["claims"][0].update(
        kind="factual",
        text="Prepare the order confirmation and both dated seller messages.",
        evidence_ids=["message:m"],
    )
    state["candidate_batch"]["units"][1]["claims"][0]["text"] = (
        "Delivery was due on 12 October and 14 October."
    )
    approve_all(state)
    state["unit_review"]["claims"][1].update(
        support="unsupported",
        findings=[
            {
                "code": "conflicting_dates",
                "severity": "major",
                "reason": "Clarify which commitment applied",
            }
        ],
    )
    result = pipeline().verify_and_compose(state)
    assert "Prepare the order confirmation" in result["response"]
    assert "12 October and 14 October" not in result["response"]
    assert not result["approved_documents"]


def test_half_a_letter_is_not_exported():
    state = mixed_fixture()
    state["candidate_batch"]["units"][1]["document_claim_ids"] += ["unsafe"]
    approve_all(state)
    result = pipeline().verify_and_compose(state)
    assert "Please arrange a refund" in result["response"]
    assert result["approved_documents"] == []


@pytest.mark.parametrize("language", ["hi", "hinglish"])
def test_partial_notice_and_fallback_follow_language(language):
    state = mixed_fixture()
    state["language"] = language
    result = pipeline().verify_and_compose(state)
    assert ("उपलब्ध जानकारी" if language == "hi" else "Available jaankari") in result["response"]


def test_general_search_parser_does_not_use_consumer_allowlist():
    urls = [
        "https://www.fssai.gov.in/page",
        "https://rbi.org.in/page",
        "https://www.fda.gov/food",
        "https://www.goibibo.com/support",
    ]
    parsed = parse_source_candidates(
        {"output": [{"sources": [{"url": url, "title": "Fixture"} for url in urls]}]}
    )
    assert {p["url"] for p in parsed} == set(urls)


def test_public_search_adapter_keeps_nonconsumer_results_and_bounded_sdk_call(monkeypatch):
    captured = {}
    urls = ["https://fssai.gov.in/page", "https://rbi.org.in/page", "https://www.fda.gov/page"]

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda **k: {
                "output": [
                    {
                        "type": "web_search_call",
                        "status": "completed",
                        "action": {"sources": [{"url": u} for u in urls]},
                    }
                ],
                "usage": {"input_tokens": 1},
            }
        )

    class FakeSDK:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0

        def __enter__(self):
            return SimpleNamespace(responses=SimpleNamespace(create=create))

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("app.services.web_research.OpenAI", FakeSDK)
    results, usage = OfficialSearchProvider(Settings(openai_api_key="fixture")).search_public(
        "official public procedure", 5
    )
    assert {r["url"] for r in results} == set(urls)
    assert "filters" not in captured["tools"][0]
    assert captured["max_tool_calls"] == 1 and captured["store"] is False
    assert usage["discovery_counts"]["parsed_url_count"] == 3


def test_legal_destination_cannot_hide_as_general_information():
    state = public_fixture()
    claim = state["candidate_batch"]["units"][0]["claims"][0]
    claim.update(kind="general", text="You should file your complaint with the RBI Ombudsman.")
    approve_all(state)
    assert pipeline().verify_and_compose(state)["published_passage_ids"] == []


def test_fraud_never_queries_consumer_vectors(tmp_path):
    settings = Settings(openai_api_key=None, chroma_path=tmp_path)
    retriever = HybridRetriever(settings)
    retriever.collection = SimpleNamespace(
        query=lambda **kwargs: pytest.fail("Consumer vectors accessed for fraud")
    )
    context = TaskContext.for_task(task(domain="criminal", risk_level="urgent"))
    assert retriever.search("unauthorized debit", task_context=context) == []


def test_drafting_flag_does_not_prevent_fact_proposals():
    parsed = interpretation(
        task(
            intent="draft",
            domain="consumer",
            relationship="buyer and seller",
            case_link="uncertain",
            requires_case_update=False,
        )
    )
    assert WorkflowPolicy.investigate_tasks(parsed)
    assert not WorkflowPolicy.case_tasks(parsed, CaseMemory())


def test_review_failure_keeps_unchanged_previously_approved_claims():
    state = mixed_fixture()
    service = pipeline()
    # Every model interaction is a deterministic local double.
    service.model = lambda *args, **kwargs: SimpleNamespace(
        invoke=lambda messages: {
            "parsed": UnitReviewBatch.model_validate(state["unit_review"]),
            "raw": None,
        }
    )
    state.update(service.review(state))
    assert state["verified_claim_reviews"]
    state["candidate_batch"]["units"][0]["claims"][0]["text"] = (
        "Repaired but unreviewed safety assertion"
    )

    def fail(messages):
        raise TimeoutError("Synthetic review failure")

    service.model = lambda *args, **kwargs: SimpleNamespace(invoke=fail)
    state.update(service.review(state))
    result = service.verify_and_compose(state)
    assert "Please arrange a refund" in result["response"]
    assert "unreviewed safety assertion" not in result["response"]
    state["candidate_batch"]["units"][1]["claims"][0]["text"] += " Changed words."
    assert not service.verify_and_compose(state)["approved_documents"]


def test_review_evidence_change_invalidates_cached_approval():
    state = public_fixture()
    service = pipeline()
    service.model = lambda *a, **k: SimpleNamespace(
        invoke=lambda m: {
            "parsed": UnitReviewBatch.model_validate(state["unit_review"]),
            "raw": None,
        }
    )
    state.update(service.review(state))
    state["unit_review"] = {}
    state["passages"][0]["text"] = "Different text under the same ID."
    assert service.verify_and_compose(state)["published_passage_ids"] == []


def test_generation_reserves_review_capacity_without_constructing_model():
    state = mixed_fixture()
    state["model_calls"] = 100
    assert pipeline().generate(state)["events"][0]["status"] == "budget_exhausted"


def test_context_carries_followups_drafts_ist_and_contradictions():
    state = mixed_fixture()
    state["context"] = {
        "recent_turns": [{"role": "assistant", "content": "Previous summary"}],
        "current_drafts": [{"content": "User edited letter"}],
        "runtime": {"timezone": "Asia/Kolkata"},
        "contradictions": [{"description": "Two dates conflict"}],
    }
    payload, _, _ = pipeline().payload(state)
    assert payload["runtime"]["timezone"] == "Asia/Kolkata"
    assert payload["conversation_context"]["current_drafts"][0]["content"] == "User edited letter"
    assert payload["conversation_context"]["contradictions"]


def test_compiled_http_mixed_partial_response_persists_and_retries_once(
    client, isolated_app, monkeypatch
):
    from app.services.intake import deterministic_extract

    graph = isolated_app.state.assistant_graph
    graph.settings.openai_api_key = "synthetic-not-a-real-key"
    graph.settings.max_model_calls_per_turn = 5
    fixture = mixed_fixture()
    graph.interpreter = SimpleNamespace(
        interpret=lambda *a: (
            interpretation(*[task(**t) for t in fixture["interpretation"]["tasks"]]),
            {},
            "synthetic_fixture",
        )
    )
    monkeypatch.setattr(
        graph.intake, "extract", lambda text, *args: (deterministic_extract(text), {})
    )
    graph.task_research = SimpleNamespace(
        run=lambda t, state, **k: (
            {
                "tool": "web_search",
                "task_id": t.task_id,
                "status": "execution_failed",
                "source_ids": [],
                "error_type": "SyntheticTimeout",
            },
            [],
            state["model_calls"],
            {},
        )
    )
    calls = []

    def fake_model(schema, review=False):
        def invoke(messages):
            calls.append(schema.__name__)
            payload = json.loads(messages[-1][1])
            if schema == UnitReviewBatch:
                return {
                    "parsed": UnitReviewBatch.model_validate(fixture["unit_review"]),
                    "raw": None,
                }
            batch = copy.deepcopy(fixture["candidate_batch"])
            message = next(
                e["evidence_id"] for e in payload["evidence"] if e["kind"] == "user_report"
            )
            batch["units"][1]["claims"][0]["evidence_ids"] = [message]
            return {"parsed": CandidateBatch.model_validate(batch), "raw": None}

        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(graph.unit_pipeline, "model", fake_model)
    cid = create_case(client)
    body = {"content": fixture["current_message"], "request_id": str(uuid.uuid4())}
    reply = client.post(f"/api/conversations/{cid}/turns", json=body)
    assert reply.status_code == 200, reply.text
    data = reply.json()
    assert "Please arrange a refund" in data["assistant_message"]["content"]
    assert "safe to drink" not in data["assistant_message"]["content"]
    assert data["assistant_message"]["metadata"]["publication_status"] == "partial"
    assert data["sources"] == []
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["drafts"][0]["content"].startswith("The milk")
    assert detail["case_proposals"]
    assert detail["case_memory"]["domain"] == "unknown"
    assert client.post(f"/api/conversations/{cid}/turns", json=body).status_code == 200
    assert calls == ["CandidateBatch", "UnitReviewBatch"]
    assert len(client.get(f"/api/conversations/{cid}").json()["messages"]) == 2


def test_staged_proposals_are_atomic_owner_scoped_and_deleted(client, isolated_app):
    cid = create_case(client)
    db = isolated_app.state.db
    with db.connect() as conn:
        owner = conn.execute("SELECT owner_id FROM conversations WHERE id=?", (cid,)).fetchone()[0]
    staged = {
        "message_id": "fixture-m",
        "task_ids": ["task-1"],
        "memory": {"facts": {"amount": {"value": "800"}}},
    }
    db.save_memory(
        cid, CaseMemory(), "", expected_version=0, owner_id=owner, staged_proposal=staged
    )
    assert db.case_proposals(owner, cid)[0]["proposed_facts"]["amount"]["value"] == "800"
    assert db.load_memory(owner, cid)[0].facts == {}
    with pytest.raises(KeyError):
        db.case_proposals("other-owner", cid)
    db.save_memory(cid, CaseMemory(version=1), "", expected_version=0, owner_id=owner)
    with pytest.raises(MemoryConflict):
        db.save_memory(
            cid,
            CaseMemory(version=2),
            "",
            expected_version=0,
            owner_id=owner,
            staged_proposal={**staged, "message_id": "rollback"},
        )
    assert len(db.case_proposals(owner, cid)) == 1
    client.delete(f"/api/conversations/{cid}").raise_for_status()
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM staged_case_updates WHERE conversation_id=?", (cid,)
            ).fetchone()[0]
            == 0
        )


def test_confidence_categories_and_action_recommendations_calibrated_certainty():
    state = public_fixture()
    state["interpretation"] = interpretation(
        task(
            task_id="task-1",
            domain="consumer",
            intent="legal_options",
            source_text="Whom should I approach and what should my complaint say?",
        ),
        task(
            task_id="task-2",
            domain="consumer",
            intent="draft",
            source_text="what should my complaint say?",
        ),
    ).model_dump(mode="json")
    state["interpretation"]["requested_deliverables"] = ["escalation_guidance", "complaint_draft"]
    state["candidate_batch"]["units"] = [
        {
            "unit_id": "u-options",
            "task_id": "task-1",
            "claims": [
                {
                    "claim_id": "rec-1",
                    "kind": "recommendation",
                    "text": "You have reasonable grounds to dispute the booking and request a full refund because the listing reportedly permitted guests aged 18 while the hotel gave inconsistent age rules of 19 and 21.",
                    "evidence_ids": ["message:m"],
                    "depends_on": [],
                },
                {
                    "claim_id": "unverified-law",
                    "kind": "recommendation",
                    "text": "The hotel is legally required under Section 2(47) of the Consumer Protection Act, 2019 to refund your booking.",
                    "evidence_ids": ["message:m"],
                    "depends_on": [],
                },
            ],
            "action_recommendations": [
                {
                    "action": "Contact Goibibo support and the hotel manager in writing to request a full refund.",
                    "rationale_claim_ids": ["rec-1"],
                    "evidence_ids": [],
                    "prerequisites": ["Booking ID", "Payment receipt"],
                    "limitations": ["Subject to verified booking terms"],
                },
                {
                    "action": "File a complaint with the Consumer Commission under Section 35.",
                    "rationale_claim_ids": ["rec-1"],
                    "evidence_ids": [],
                    "prerequisites": [],
                    "limitations": [],
                },
            ],
            "unresolved": ["Missing booking ID and payment amount"],
            "document_title": None,
            "document_claim_ids": [],
        },
        {
            "unit_id": "u-draft",
            "task_id": "task-2",
            "claims": [
                {
                    "claim_id": "draft-1",
                    "kind": "draft",
                    "text": "Subject: Denied check-in and refund request — Booking ID: [Booking ID]\n\nI request a full refund of ₹[amount] to my original payment method, without cancellation deductions, because the hotel refused check-in despite the eligibility information displayed when I booked.",
                    "evidence_ids": ["message:m"],
                    "depends_on": [],
                },
                {
                    "claim_id": "prep-1",
                    "kind": "preparation",
                    "text": "Before sending: replace [Booking ID] and [amount] and attach the Goibibo listing screenshot and payment receipt.",
                    "evidence_ids": ["message:m"],
                    "depends_on": [],
                },
            ],
            "action_recommendations": [],
            "unresolved": ["Missing booking ID and payment amount"],
            "document_title": "Prepared correspondence",
            "document_claim_ids": ["draft-1"],
        },
    ]
    approve_all(state)
    state["unit_review"]["unresolved_claims"] = [
        {
            "claim_id": "unverified-law",
            "explanation": "The hotel's booking-specific age policy and applicable cancellation conditions have not yet been verified.",
        }
    ]
    state["reviewed_context_digest"] = review_binding(state)
    result = pipeline().verify_and_compose(state)
    assert "You have reasonable grounds to dispute the booking and request a full refund" in result["response"]
    assert "legally required under Section 2(47)" not in result["response"]
    assert "Before sending: replace [Booking ID]" in result["response"]
    assert "without cancellation deductions" in result["approved_documents"][0]["content"]
    assert (
        "One part of this request remains unverified; the supported material above is available to use as provisional preparation."
        not in result["response"]
    )
    assert (
        "The hotel's booking-specific age policy and applicable cancellation conditions have not yet been verified."
        in result["response"]
    )
    u_options = next(u for u in result["unit_outcomes"] if u["unit_id"] == "u-options")
    u_draft = next(u for u in result["unit_outcomes"] if u["unit_id"] == "u-draft")
    # Internal unresolved placeholder notes must not degrade a fully supported draft unit to partial.
    assert u_draft["status"] == "supported"
    # Ordinary practical action recommendation is preserved; unverified Commission filing recommendation is filtered.
    assert len(u_options["action_recommendations"]) == 1
    assert "Goibibo support" in u_options["action_recommendations"][0]["action"]


def test_usefulness_review_and_quality_scorecard_do_not_override_safety():
    state = public_fixture()
    state["interpretation"]["requested_deliverables"] = ["escalation_guidance", "complaint_draft"]
    approve_all(state)
    state["unit_review"]["usefulness_review"] = {
        "requested_deliverables_complete": False,
        "primary_question_answered": True,
        "recommended_action_clear": False,
        "important_supported_facts_preserved": True,
        "avoidable_clarification": True,
        "unnecessary_disclaimer": False,
    }
    state["reviewed_context_digest"] = review_binding(state)
    service = pipeline()
    assert service.verifier.needs_usefulness_repair(state) is True

    # Verify that serious safety failures cannot be compensated by high usefulness scores
    unsafe_state = mixed_fixture()
    result = service.verify_and_compose(unsafe_state)
    scorecard = result["verification"]["quality_scorecard"]
    assert scorecard["serious_safety_failure"] is True
    assert scorecard["factual_and_legal_accuracy"] == 0.0
