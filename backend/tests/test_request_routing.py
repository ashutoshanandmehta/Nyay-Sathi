"""Offline contracts and explicitly labelled provider doubles; no live API calls."""

import copy
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db import MemoryConflict
from app.routing.contracts import (
    CaseUpdateProposal,
    EntityMention,
    RequestInterpretation,
    TaskIntent,
)
from app.routing.entities import EntityResolver
from app.routing.interpretation import ContextualInterpreter, conservative_interpretation
from app.routing.policy import CapabilityRegistry, PublicQueryPolicy, WorkflowPolicy
from app.routing.research import TaskResearchService, public_https_url
from app.routing.state_manager import CaseStateManager, UnauthorizedCaseUpdate
from app.routing.validation import ExecutionValidator
from app.schemas.models import CaseMemory
from app.services.intake import deterministic_extract

from .conftest import create_case


def task(**updates):
    data = dict(
        task_id="task-1",
        source_text="A synthetic request",
        intent="information",
        domain="general",
        relationship=None,
        entities=[],
        case_link="unrelated",
        requires_research=False,
        requires_case_update=False,
        risk_level="ordinary",
        uncertainty=[],
        public_query=None,
    )
    return TaskIntent(**{**data, **updates})


def interpretation(*tasks):
    return RequestInterpretation(
        tasks=list(tasks),
        case_relevance="mixed" if len(tasks) > 1 else tasks[0].case_link,
        clarification_needed=False,
    )


def send(client, cid, content):
    result = client.post(
        f"/api/conversations/{cid}/turns",
        json={"content": content, "request_id": str(uuid.uuid4())},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize(
    "message,domain",
    [
        ("My salary at a hotel is unpaid", "employment"),
        ("I ordered a hotel stay and the seller refused my refund", "consumer"),
        ("Can you search whether I can feed cucumber to my cow?", "animal_health"),
        ("When did Jio release its IPO?", "general"),
        ("मेरा वेतन नहीं मिला, होटल में काम करता हूँ", "employment"),
        ("Maine monitor mangaya lekin delivery nahi mili", "consumer"),
        ("My landlord kept the deposit", "tenancy"),
        ("Police may arrest me", "criminal"),
    ],
)
def test_labelled_offline_relationship_regressions(message, domain):
    result = conservative_interpretation(message, {})
    assert result.tasks[0].domain == domain
    if domain == "employment":
        assert deterministic_extract(message).domain != "consumer"


def test_industry_and_brand_words_alone_do_not_choose_consumer():
    for text in ["What is a hotel?", "Tell me about Blinkit", "What does booking mean?"]:
        assert conservative_interpretation(text, {}).tasks[0].domain == "general"


def test_model_contract_runs_without_case_tools_and_preserves_multiple_requests():
    text = "Is this milk safe? Draft a refund request."
    output = interpretation(
        task(source_text="Is this milk safe?", domain="health", requires_research=True),
        task(
            task_id="task-2",
            source_text="Draft a refund request.",
            domain="consumer",
            intent="draft",
            case_link="new",
            requires_case_update=True,
        ),
    )
    captured = []

    class LabelledModel:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0

        def with_structured_output(self, schema, **kwargs):
            from app.routing.segments import SegmentInterpretation
            assert schema is SegmentInterpretation
            return self

        def invoke(self, messages):
            captured.extend(messages)
            return {"parsed": output, "raw": SimpleNamespace(usage_metadata={"total_tokens": 4})}

    context = {"case_domain": "unknown"}
    saved = copy.deepcopy(context)
    value, usage, status = ContextualInterpreter(
        Settings(openai_api_key="labelled-fixture"), LabelledModel
    ).interpret(text, context)
    assert context == saved and len(value.tasks) == 2 and status == "model"
    assert usage["total_tokens"] == 4
    assert "no tools" in captured[0][1]
    assert {p.workflow for p in WorkflowPolicy.plan(value)} == {"safety", "consumer"}


def test_contract_rejects_model_case_ids_and_duplicate_task_ids():
    with pytest.raises(ValidationError):
        RequestInterpretation(
            **{**interpretation(task()).model_dump(), "active_case_id": "foreign"}
        )
    with pytest.raises(ValidationError):
        interpretation(task(), task())


def test_general_write_proposal_is_not_permission():
    value = interpretation(task(requires_case_update=True, case_link="existing"))
    assert not WorkflowPolicy.case_tasks(value, CaseMemory())


def test_unknown_organization_is_a_mention_not_an_eligible_authority():
    value = interpretation(
        task(
            domain="employment",
            entities=[
                EntityMention(
                    name="Silver Lotus Lodge",
                    kind="organization",
                    role="employer",
                    identity_status="mentioned",
                )
            ],
        )
    )
    records = EntityResolver().candidates(value)
    assert records[0]["profile_id"] is None
    assert records[0]["authority_eligibility"] == "not_established"
    assert WorkflowPolicy.plan(value)[0].workflow == "legal_handoff"


def test_urgent_task_precedes_other_tasks_without_consumer_inference():
    value = interpretation(task(), task(task_id="task-2", domain="health", risk_level="urgent"))
    assert WorkflowPolicy.plan(value)[0].task_id == "task-2"
    assert WorkflowPolicy.plan(value)[0].workflow == "safety"


def test_general_questions_and_ambiguous_yes_preserve_case_and_edited_draft(client, isolated_app):
    cid = create_case(client)
    send(client, cid, "My defective phone cost ₹18,000")
    db = isolated_app.state.db
    with db.connect() as conn:
        oid = conn.execute("SELECT owner_id FROM conversations WHERE id=?", (cid,)).fetchone()[0]
    draft = db.create_draft(oid, cid, "User edited", "Keep my exact words", 1)
    before = client.get(f"/api/conversations/{cid}").json()["case_memory"]
    for question in [
        "When did Jio release its IPO?",
        "Yes, that's right.",
        "Can I feed cucumber to my cow?",
    ]:
        result = send(client, cid, question)
        after = client.get(f"/api/conversations/{cid}").json()["case_memory"]
        assert after == before
        assert not result["assistant_message"]["metadata"]["resolution_plan"]
    saved = db.drafts(oid, cid)[0]
    assert saved["id"] == draft["id"] and saved["content"] == "Keep my exact words"
    assert saved["status"] != "stale"
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM case_update_audit WHERE conversation_id=? AND decision='no_case_change'",
                (cid,),
            ).fetchone()[0]
            == 3
        )


def test_employment_request_never_recommends_nch(client):
    cid = create_case(client)
    result = send(client, cid, "My salary at a hotel is unpaid. What should I do?")
    detail = client.get(f"/api/conversations/{cid}").json()
    assert detail["case_memory"]["domain"] == "employment"
    assert result["assistant_message"]["metadata"]["resolution_plan"] == {}
    assert result["assistant_message"]["metadata"]["task_plan"][0]["workflow"] == "legal_handoff"


def test_mixed_legal_and_general_tasks_only_commit_legal_amount(client):
    cid = create_case(client)
    result = send(client, cid, "My refund of ₹800 is late? When did Jio release its IPO?")
    memory = client.get(f"/api/conversations/{cid}").json()["case_memory"]
    assert memory["facts"]["amount"]["value"] == "800"
    assert len(result["assistant_message"]["metadata"]["task_plan"]) == 2
    assert "Jio" not in str(memory)


def test_new_domain_does_not_overwrite_existing_case(client):
    cid = create_case(client)
    send(client, cid, "My refund of ₹800 is late")
    before = client.get(f"/api/conversations/{cid}").json()["case_memory"]
    send(client, cid, "My employer owes my salary at a hotel")
    assert client.get(f"/api/conversations/{cid}").json()["case_memory"] == before


def test_proposal_unauthorized_mutation_is_rejected():
    before = CaseMemory()
    after = CaseMemory(domain="consumer", version=1)
    proposal = CaseUpdateProposal(
        base_version=0,
        source_message_id="m",
        source_task_ids=[],
        proposed_memory=after.model_dump(mode="json"),
        summary="",
    )
    with pytest.raises(UnauthorizedCaseUpdate):
        CaseStateManager.validate(before, proposal, interpretation(task()))


def test_concurrent_conflict_rolls_back_draft_invalidation_and_audit(client, isolated_app):
    cid = create_case(client)
    db = isolated_app.state.db
    with db.connect() as conn:
        owner = conn.execute("SELECT owner_id FROM conversations WHERE id=?", (cid,)).fetchone()[0]
    db.create_draft(owner, cid, "Edited", "Preserve me", 0)
    db.save_memory(cid, CaseMemory(version=1), "")
    with pytest.raises(MemoryConflict):
        db.save_memory(
            cid,
            CaseMemory(version=2),
            "",
            expected_version=0,
            owner_id=owner,
            invalidate_drafts=True,
            audit={"message_id": "m", "task_ids": [], "decision": "bad"},
        )
    assert db.drafts(owner, cid)[0]["status"] != "stale"
    with db.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM case_update_audit WHERE conversation_id=?", (cid,)
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://example.internal",
        "https://user:password@example.com",
        "https://example.com:8443",
    ],
)
def test_public_fetch_policy_rejects_unsafe_destinations(url):
    assert not public_https_url(url)


@pytest.mark.parametrize(
    "query",
    [
        "Email user@example.com",
        "ticket: ABC123",
        "₹800 refund",
        "account number 23456789",
        "https://private.example/doc",
    ],
)
def test_public_query_rejects_identifiers(query):
    with pytest.raises(ValueError):
        PublicQueryPolicy.validate(query, {})


def test_public_query_rejects_private_case_names():
    with pytest.raises(ValueError):
        PublicQueryPolicy.validate(
            "Ash Example refund", {"parties": [{"name": "Ash Example", "role": "complainant"}]}
        )


@pytest.mark.parametrize(
    "enabled,key,calls,expected",
    [
        (False, "fixture", 0, "disabled"),
        (True, None, 0, "configuration_required"),
        (True, "fixture", 7, "budget_exhausted"),
        (True, "fixture", 0, "available"),
    ],
)
def test_capability_status_comes_from_runtime(enabled, key, calls, expected):
    config = Settings(openai_api_key=key, web_research_enabled=enabled)
    assert CapabilityRegistry(config).snapshot(calls)["web_search"]["status"] == expected


class LabelledSearch:
    def __init__(self, mode="success"):
        self.mode = mode

    def search_public(self, query, timeout):
        if self.mode == "failure":
            raise TimeoutError("Synthetic failure only")
        return ([] if self.mode == "empty" else [{"url": "https://example.edu/research"}]), {
            "total_tokens": 6
        }


class LabelledFetch:
    def read(self, candidate, timeout):
        return {
            "source_id": "synthetic-source",
            "url": candidate["url"],
            "hash": "fixture",
            "raw": b"synthetic",
            "passages": [
                {
                    "passage_id": "synthetic-p1",
                    "source_id": "synthetic-source",
                    "text": "Synthetic fixture: company IPO status has not been established.",
                    "title": "Synthetic research",
                    "locator": "Page 1",
                    "canonical_url": candidate["url"],
                }
            ],
        }


class LabelledRepository:
    def save(self, *args):
        self.args = args


@pytest.mark.parametrize(
    "mode,expected",
    [("success", "succeeded"), ("failure", "execution_failed"), ("empty", "no_supporting_results")],
)
def test_public_research_records_actual_execution(mode, expected):
    service = TaskResearchService(
        Settings(openai_api_key="fixture"),
        LabelledSearch(mode),
        LabelledFetch(),
        LabelledRepository(),
    )
    record, passages, calls, usage = service.run(
        task(requires_research=True, public_query="company IPO status official filings"),
        {
            "owner_id": "trusted-owner",
            "conversation_id": "trusted-case",
            "message_id": "m",
            "context": {},
        },
        documents_remaining=1,
    )
    assert record["status"] == expected and calls == 1
    if passages:
        assert passages[0]["verification_status"] == "unverified_public_source"
        assert passages[0]["effective_date"] is None and passages[0]["jurisdiction"] is None


def test_search_claim_without_execution_fails():
    findings = ExecutionValidator.check(
        {"response": "I searched the web and found this.", "tool_records": []}
    )
    assert findings[0]["code"] == "unexecuted_search_claim"


def test_unverified_authority_cannot_be_declared_eligible():
    state = {
        "response_envelope": {
            "legal_recommendations": [
                {
                    "route_id": "invented",
                    "status": "eligible_destination",
                    "passage_ids": ["p"],
                    "jurisdiction": "India",
                    "effective_date": "2026-01-01",
                }
            ]
        },
        "passages": [],
    }
    assert ExecutionValidator.check(state)[0]["code"] == "unverified_legal_destination"


def test_two_requests_need_two_coverage_records():
    value = interpretation(task(), task(task_id="task-2"))
    state = {
        "interpretation": value.model_dump(mode="json"),
        "request_coverage": [{"request_id": "task-1", "status": "answered", "reason": None}],
    }
    assert any(f["code"] == "task_coverage_missing" for f in ExecutionValidator.check(state))


def test_failed_interpretation_cannot_write_case(client, isolated_app):
    cid = create_case(client)

    class FailingInterpreter:
        def interpret(self, *args):
            raise ValueError("Synthetic malformed contract")

    isolated_app.state.assistant_graph.interpreter = FailingInterpreter()
    result = send(client, cid, "My refund of ₹800 is late")
    assert client.get(f"/api/conversations/{cid}").json()["case_memory"]["version"] == 0
    assert result["assistant_message"]["metadata"]["case_update_allowed"] is False


def test_typed_mixed_contract_executes_before_intake_and_scopes_its_input(
    client, isolated_app, monkeypatch
):
    cid = create_case(client)
    graph = isolated_app.state.assistant_graph
    legal = "My refund of ₹800 is late."
    general = "Search current company IPO status."
    order = []

    class LabelledInterpreter:
        def interpret(self, message, context):
            order.append("interpret")
            return (
                interpretation(
                    task(
                        source_text=legal,
                        domain="consumer",
                        intent="case_update",
                        case_link="new",
                        requires_case_update=True,
                    ),
                    task(
                        task_id="task-2",
                        source_text=general,
                        intent="search",
                        requires_research=True,
                        public_query="company IPO status official filings",
                    ),
                ),
                {},
                "offline_fixture",
            )

    original = graph.intake.extract

    def intake(text, context, guidance):
        order.append("intake")
        assert text == legal and "IPO" not in text
        return original(text, context, guidance)

    graph.interpreter = LabelledInterpreter()
    monkeypatch.setattr(graph.intake, "extract", intake)
    result = send(client, cid, legal + " " + general)
    assert order == ["interpret", "intake"]
    assert [r["workflow"] for r in result["assistant_message"]["metadata"]["task_plan"]] == [
        "consumer",
        "general",
    ]


def test_new_dispute_cannot_be_merged_by_its_update_flag():
    value = interpretation(
        task(domain="consumer", intent="case_update", case_link="new", requires_case_update=True)
    )
    assert not WorkflowPolicy.case_tasks(value, CaseMemory(domain="consumer", version=2))


def test_preparation_only_policy_cannot_establish_filing_eligibility():
    state = {
        "response_envelope": {
            "legal_recommendations": [
                {
                    "route_id": "nch",
                    "status": "eligible_destination",
                    "passage_ids": ["p"],
                    "jurisdiction": "India",
                    "effective_date": "2026-01-01",
                }
            ]
        },
        "passages": [
            {
                "passage_id": "p",
                "source_type": "official_public",
                "jurisdiction": "India",
                "effective_date": "2026-01-01",
            }
        ],
        "resolution_plan": {
            "alternatives": [
                {
                    "route_id": "nch",
                    "eligibility": {
                        "status": "eligible",
                        "scope": "preparation",
                        "filing_verified": False,
                    },
                }
            ]
        },
    }
    assert any(f["code"] == "unverified_legal_destination" for f in ExecutionValidator.check(state))


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("calendar_arithmetic", "date_arithmetic_error"),
        ("statutory_deadline", "unverified_statutory_clock"),
    ],
)
def test_calendar_arithmetic_does_not_determine_legal_deadlines(kind, expected):
    state = {
        "response_envelope": {
            "date_calculations": [
                {
                    "kind": kind,
                    "start_date": "2026-11-06",
                    "days": 3,
                    "result_date": "2026-11-08",
                    "rule_id": None,
                }
            ]
        }
    }
    assert any(f["code"] == expected for f in ExecutionValidator.check(state))


def test_missing_mandatory_fields_prevent_send_ready_claim():
    state = {
        "response_envelope": {"document_ready_to_send": True},
        "draft_spec": {"missing_details": ["parties and address"]},
    }
    assert ExecutionValidator.check(state)[0]["code"] == "document_not_send_ready"


def test_private_evidence_excerpts_are_not_public_queries():
    with pytest.raises(ValueError):
        PublicQueryPolicy.validate(
            "unique details written in private document",
            {
                "relevant_evidence": [
                    {
                        "text": "These unique details written in private document must not leave this workspace."
                    }
                ]
            },
        )


def test_contextual_query_respects_missing_year_and_false_premise_contract():
    value = interpretation(
        task(
            source_text="When did Jio release its IPO?",
            intent="search",
            requires_research=True,
            uncertainty=["Whether an IPO occurred and which entity is meant"],
            public_query="Jio Platforms whether IPO launched official filings current status",
        )
    )
    assert "whether" in value.tasks[0].public_query
    assert value.tasks[0].uncertainty
    assert value.model_dump().get("active_case_id") is None


def test_false_search_limitation_is_rejected_when_execution_succeeded():
    state = {
        "response": "I can't perform a live web search in this chat.",
        "tool_records": [{"tool": "web_search", "task_id": "task-1", "status": "succeeded"}],
    }
    assert ExecutionValidator.check(state)[0]["code"] == "false_search_limitation"


def test_planning_metadata_does_not_count_as_a_material_draft_change():
    before = CaseMemory(domain="consumer", version=1)
    after = before.model_copy(deep=True)
    after.version = 2
    after.pending_questions = [{"question": "What remedy do you want?"}]
    assert CaseStateManager.material_snapshot(before) == CaseStateManager.material_snapshot(after)


def test_completed_search_without_support_can_be_reported_honestly():
    state = {
        "response": "I searched the web, but found no supporting results.",
        "tool_records": [
            {
                "tool": "web_search",
                "task_id": "task-1",
                "status": "no_supporting_results",
                "search_completed": True,
            }
        ],
    }
    assert ExecutionValidator.check(state) == []


def test_available_search_cannot_be_described_as_unavailable():
    state = {
        "response": "I can't perform a live web search in this chat.",
        "capabilities": {"web_search": {"status": "available"}},
    }
    assert ExecutionValidator.check(state)[0]["code"] == "false_search_limitation"


def test_public_fetch_rejects_dns_resolving_to_private_network(monkeypatch):
    from app.rag.ingest import validate_url

    monkeypatch.setattr(
        "app.rag.ingest.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.1", 443))],
    )
    with pytest.raises(ValueError):
        validate_url("https://unknown-business.example/path", url_policy=public_https_url)


def test_unrelated_proposal_cannot_rewrite_only_the_summary(client, isolated_app):
    cid = create_case(client)
    db = isolated_app.state.db
    with db.connect() as conn:
        owner = conn.execute("SELECT owner_id FROM conversations WHERE id=?", (cid,)).fetchone()[0]
    before, _ = db.load_memory(owner, cid)
    proposal = CaseUpdateProposal(
        base_version=0,
        source_message_id="m",
        source_task_ids=[],
        proposed_memory=before.model_dump(mode="json"),
        summary="Invented replacement summary",
    )
    with pytest.raises(UnauthorizedCaseUpdate):
        CaseStateManager(db).commit(
            owner_id=owner,
            conversation_id=cid,
            before=before,
            proposal=proposal,
            interpretation=interpretation(task()),
            graph_state={},
        )
    assert db.load_memory(owner, cid)[1] == ""


def test_outcome_first_goibibo_interpretation_and_whitespace_normalized_spans():
    prompt = (
        "I booked a hotel on Goibibo where it showed 18 year olds are allowed.\n\n"
        "At check-in they denied entry saying minimum age is 19, then later said 21.\n\n"
        "They promised refund on call, and when I raised cancellation they rejected it.\n\n"
        "Whom should I approach and what should my complaint say?"
    )
    fallback = conservative_interpretation(prompt, {})
    assert {t.intent for t in fallback.tasks} == {"legal_options", "draft"}
    assert fallback.requested_deliverables == ["escalation_guidance", "complaint_draft"]
    assert fallback.user_goal == "recover_booking_payment"
    assert fallback.suggested_remedy == "request_full_refund"
    assert {
        "explain_factual_discrepancy",
        "identify_initial_recipient",
        "provide_escalation_options",
        "draft_refund_request",
        "identify_essential_evidence",
    } <= set(fallback.required_answer_elements)
    assert "booking_id" in fallback.missing_details
    assert "payment_amount" in fallback.missing_details

    # Verify whitespace-normalized source_text span matching in ContextualInterpreter
    normalized_source = " ".join(prompt.split())
    model_output = interpretation(
        task(
            task_id="task-1",
            source_text=normalized_source,
            intent="legal_options",
            domain="consumer",
            case_link="new",
            requires_research=True,
            requires_case_update=True,
        ),
        task(
            task_id="task-2",
            source_text="what should my complaint say?",
            intent="draft",
            domain="consumer",
            case_link="new",
            requires_research=False,
            requires_case_update=True,
        ),
    )

    class NormalizedSpanModel:
        def __init__(self, **kwargs):
            pass

        def with_structured_output(self, schema, **kwargs):
            return self

        def invoke(self, messages):
            return {"parsed": model_output, "raw": SimpleNamespace(usage_metadata={})}

    parsed, _, status = ContextualInterpreter(
        Settings(openai_api_key="labelled-fixture"), NormalizedSpanModel
    ).interpret(prompt, {})
    assert status == "model"
    assert parsed.user_goal == "recover_booking_payment"
    assert parsed.suggested_remedy == "request_full_refund"
    assert parsed.requested_deliverables == ["escalation_guidance", "complaint_draft"]
