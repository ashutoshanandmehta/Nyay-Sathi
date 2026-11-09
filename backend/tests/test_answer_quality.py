"""Answer-quality fixes: review routing, lawyer referral, honest fallback, repairs and official packs.

Offline: scripted model outputs and the local index only. These test software behaviour, not
legal correctness of a live model's answers.
"""

import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.budget import TurnBudget
from app.agent.contracts import AgentAnswer, AgentReview, AgentTask, AnswerClaim, ClaimVerdict
from app.agent.runner import PrimaryAgent
from app.agent.safety import detect_india_context
from app.agent.verification import mechanical_checks, template_text
from app.answers.evidence import EvidenceRegistry
from app.config import Settings
from app.knowledge.search_index import OFFICIAL_PACKS_PATH, OpenSearchLegalIndex
from app.rag.retrieval import HybridRetriever
from app.routing.segments import segment_message
from tests.conftest import create_case
from tests.test_primary_agent import ScriptedProvider, install

BIHAR_ARREST = (
    "my brother was taking my car from patna to biharsharif...the police stopped the car and "
    "found alcohol in my car....he took my brother to jail..what to do?"
)


def _task(**overrides):
    return AgentTask(
        **{
            "task_id": "task-1",
            "title": "Help",
            "intent": "legal_options",
            "domain": "criminal",
            "case_link": "new",
            **overrides,
        }
    )


def _post(client, cid, content):
    return client.post(
        f"/api/conversations/{cid}/turns",
        json={"content": content, "request_id": str(uuid.uuid4())},
    )


def _fixture_passage(passage_id="fix-law"):
    return {
        "passage_id": passage_id,
        "source_id": passage_id + "-src",
        "title": "Synthetic official fixture",
        "locator": "Section 47: Fixture",
        "text": "Section 47: a person arrested must be told the grounds of arrest.",
        "canonical_url": "https://www.example.gov.in/fixture.pdf",
        "retrieved_at": "2026-11-08T00:00:00Z",
        "origin": "official_pack",
        "source_type": "indian_official",
    }


def _research_with(*passages):
    return SimpleNamespace(
        retrieve_certified=lambda *_, **__: (list(passages), {"query_hash": "q"})
    )


# --- Phase 1: what may publish without review --------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "In a 2022 Pune consumer forum ruling, a tenant recovered the full deposit plus interest.",
        "Courts have held, as in Sharma v. Kulkarni (2019), that landlords forfeit such deductions.",
        "Landlords have 30 days to return a deposit; after that you can claim double the amount.",
        "मकान मालिक को 15 दिन के भीतर जमा राशि लौटानी होती है।",
    ],
)
def test_precedent_deadline_and_case_name_wording_cannot_skip_review(text):
    state = {"current_message": "Deposit not returned.", "memory": {"facts": {}}, "passages": []}
    claim = AnswerClaim(
        claim_id="c1",
        task_id="task-1",
        kind="practical",
        grounding="practical_precaution",
        block_type="alternatives",
        text=text,
    )
    answer = AgentAnswer(central_question="q", tasks=[_task()], claims=[claim])
    blocked, approved, pending = mechanical_checks(answer, EvidenceRegistry(state))
    assert pending == ["c1"] and not approved and not blocked


def test_plain_practical_step_still_publishes_without_a_review_call():
    state = {"current_message": "Deposit not returned.", "memory": {"facts": {}}, "passages": []}
    claim = AnswerClaim(
        claim_id="c1",
        task_id="task-1",
        kind="practical",
        grounding="practical_precaution",
        block_type="immediate_actions",
        text="Keep the rent receipts and the messages where the landlord mentions the deposit.",
    )
    answer = AgentAnswer(central_question="q", tasks=[_task()], claims=[claim])
    _, approved, pending = mechanical_checks(answer, EvidenceRegistry(state))
    assert approved == {"c1": "risk_calibrated_consistency"} and not pending


def test_reviewed_lawyer_referral_is_published_last_under_its_heading(client, isolated_app):
    cid = create_case(client)
    message = "My brother was arrested yesterday."
    seg = "segment:" + segment_message(message)[0]["id"]
    claims = [
        AnswerClaim(
            claim_id="step",
            task_id="task-1",
            kind="practical",
            grounding="practical_precaution",
            block_type="immediate_actions",
            text="Ask the police station where he is being held.",
            evidence_ids=[seg],
        ),
        AnswerClaim(
            claim_id="lawyer",
            task_id="task-1",
            kind="practical",
            grounding="practical_precaution",
            block_type="human_handoff",
            text="Involve a local criminal lawyer quickly and bring any papers the police gave you.",
            evidence_ids=[seg],
        ),
    ]
    review = AgentReview(
        claims=[
            ClaimVerdict(
                claim_id="lawyer",
                support="supported",
                reason="safe referral",
                requires_public_evidence=False,
            )
        ],
        primary_question_answered=True,
        next_action_useful=True,
    )
    install(
        isolated_app,
        ScriptedProvider(AgentAnswer(central_question="q", tasks=[_task()], claims=claims), review),
    )
    data = _post(client, cid, message).json()
    content = data["assistant_message"]["content"]
    blocks = data["assistant_message"]["metadata"]["resolution_blocks"]
    assert blocks[-1]["block_type"] == "human_handoff"
    assert blocks[-1]["title"] == "When to involve a lawyer"
    assert content.index("### When to involve a lawyer") > content.index("where he is being held")


def test_when_nothing_verifies_the_message_does_not_promise_more_below(client, isolated_app):
    cid = create_case(client)
    claim = AnswerClaim(
        claim_id="law",
        task_id="task-1",
        kind="legal",
        grounding="verified_legal_source",
        block_type="direct_answer",
        text="Section 47 requires the police to tell an arrested person why.",
        evidence_ids=["fix-law"],
    )
    review = AgentReview(
        claims=[ClaimVerdict(claim_id="law", support="unsupported", reason="fixture")],
        primary_question_answered=False,
        next_action_useful=False,
    )
    runner = install(
        isolated_app,
        ScriptedProvider(
            AgentAnswer(central_question="q", tasks=[_task()], claims=[claim]), review
        ),
        _research_with(_fixture_passage()),
    )
    runner.settings.agent_max_repairs = 0
    data = _post(client, cid, "Why was my brother arrested?").json()
    content = data["assistant_message"]["content"]
    blocks = data["assistant_message"]["metadata"]["resolution_blocks"]
    assert content.startswith(template_text("no_verified_answer", "en"))
    assert "below" not in content
    # An arrest question still ends with the lawyer / legal-aid referral, after the honest message.
    assert [b["block_type"] for b in blocks] == ["limitation", "human_handoff"]
    assert template_text("handoff_liberty", "en") in content


def test_city_or_state_names_count_as_india_for_helpline_numbers(client, isolated_app, monkeypatch):
    assert detect_india_context("Police entered our room in Patna")
    assert not detect_india_context("Police entered our room")
    seen = []

    def capture(language="en", *, india=False, category="physical_safety", today=None):
        seen.append(india)
        return {"type": "safety", "content_id": "c", "text": "Stay safe.", "sources": []}

    monkeypatch.setattr("app.agent.runner.safety_event", capture)
    cid = create_case(client)
    install(isolated_app, ScriptedProvider(TimeoutError()))
    _post(client, cid, "Police entered our room in Patna and demand money now.")
    assert seen == [True]


# --- Phase 1: caps that favour quality -----------------------------------------------------------


def test_research_cannot_spend_the_repair_reserve():
    settings = Settings(openai_api_key=None, agent_max_requests=6, agent_repair_reserve=2)
    budget = TurnBudget(settings)
    budget.reserve("fixture")
    assert budget.available(3, reserve=2) is True  # 1 used + 3 + 2 reserved = 6
    budget.reserve("fixture")
    assert budget.available(3, reserve=2) is False
    assert budget.available(2) is True  # the repair and its re-review still fit


def _repair_script(final_support):
    claim = AnswerClaim(
        claim_id="law",
        task_id="task-1",
        kind="legal",
        grounding="verified_legal_source",
        block_type="direct_answer",
        text="Draft one.",
        evidence_ids=["fix-law"],
    )
    answer = AgentAnswer(central_question="q", tasks=[_task()], claims=[claim])

    def draft(text):
        return answer.model_copy(update={"claims": [claim.model_copy(update={"text": text})]})

    def review(support):
        return AgentReview(
            claims=[ClaimVerdict(claim_id="law", support=support, reason="fixture")],
            primary_question_answered=True,
            next_action_useful=True,
        )

    return [
        answer,
        review("unsupported"),
        draft("Draft two."),
        review("unsupported"),
        draft("Draft three."),
        review(final_support),
    ]


def test_second_repair_runs_when_the_first_is_still_rejected(client, isolated_app):
    cid = create_case(client)
    provider = ScriptedProvider(*_repair_script("supported"))
    runner = install(isolated_app, provider, _research_with(_fixture_passage()))
    runner.settings.agent_max_rounds, runner.settings.agent_max_repairs = 5, 2
    meta = _post(client, cid, "Why was my brother arrested?").json()["assistant_message"]
    assert "Draft three." in meta["content"]
    assert meta["metadata"]["publication_status"] == "supported"
    attempts = [e.get("attempt") for e in meta["metadata"]["events"] if e["stage"] == "revision"]
    assert attempts == [1, 2]


def test_repairs_stop_at_the_cap_and_keep_the_answer_honest(client, isolated_app):
    cid = create_case(client)
    provider = ScriptedProvider(*_repair_script("unsupported"))
    runner = install(isolated_app, provider, _research_with(_fixture_passage()))
    runner.settings.agent_max_rounds, runner.settings.agent_max_repairs = 5, 2
    meta = _post(client, cid, "Why was my brother arrested?").json()["assistant_message"]
    assert len(provider.requests) == 6  # answer, review, then two repair + re-review pairs
    assert meta["metadata"]["publication_status"] == "partial"
    assert "Draft three." not in meta["content"]


# --- Phase 2: official knowledge packs -----------------------------------------------------------


def _pack():
    return json.loads(OFFICIAL_PACKS_PATH.read_text())


def test_pack_passages_are_sourced_hashed_and_honestly_labelled():
    pack = _pack()
    assert pack["review_status"] == "official_text_not_lawyer_reviewed"
    sources = {s["source_id"]: s for s in pack["sources"]}
    for p in pack["passages"]:
        assert p["canonical_url"].startswith("https://")
        assert p["source_id"] in sources and len(sources[p["source_id"]]["original_sha256"]) == 64
        assert p["content_hash"] == "sha256:" + hashlib.sha256(p["text"].encode()).hexdigest()
        assert p["verification_status"] == "official_text_not_lawyer_reviewed"
        assert "not reviewed by a lawyer" in p["limitations"]
    by_id = {p["passage_id"]: p for p in pack["passages"]}
    assert "(g) in custody" in by_id["pack-lsa-act-1987-s12"]["text"]
    bihar = [p for p in pack["passages"] if p["jurisdiction"] == "Bihar"]
    assert bihar and all("patna" in p["state_terms"] for p in bihar)
    act = [p for p in bihar if p["source_id"] == "bihar-prohibition-excise-act-2016"]
    assert act and all("amended in 2018 and 2022" in p["limitations"] for p in act)


def test_pack_rebuild_matches_the_committed_file():
    builder_path = Path(__file__).parents[1] / "scripts" / "build_official_packs.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_official_packs", builder_path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    if not all((builder.ORIGINALS / s["file"]).exists() for s in builder.SOURCES):
        pytest.skip("Official originals are not downloaded (data/sources/originals is gitignored)")
    rebuilt = {p["passage_id"]: p["text"] for p in builder.build()["passages"]}
    committed = {p["passage_id"]: p["text"] for p in _pack()["passages"]}
    assert rebuilt == committed


@pytest.fixture(scope="module")
def index():
    return OpenSearchLegalIndex(Settings(openai_api_key=None))


def test_state_law_is_used_only_when_the_question_names_that_state(index):
    delhi, _ = index.search("police arrested my son in delhi bail", jurisdiction="India", limit=12)
    patna, _ = index.search(
        "police found alcohol in my car in patna", jurisdiction="India", limit=12
    )
    assert not [h for h in delhi if h.get("jurisdiction") == "Bihar"]
    assert [h for h in patna if h["source_id"] == "bihar-prohibition-excise-act-2016"]
    assert all("state_terms" not in h and "keywords" not in h for h in patna)


@pytest.fixture(scope="module")
def agent():
    settings = Settings(openai_api_key=None)
    return PrimaryAgent(settings, HybridRetriever(settings), provider=object())


def _prefetch(agent, message, earlier=()):
    state = {
        "current_message": message,
        "memory": {},
        "context": {"recent_turns": [{"role": "user", "content": t} for t in earlier]},
        "passages": [],
        "tool_records": [],
    }
    agent._pre_retrieve_certified(state)
    return [p["passage_id"] for p in state["passages"]]


def test_custody_question_brings_bail_vehicle_and_free_legal_aid_law(agent):
    ids = _prefetch(agent, BIHAR_ARREST)
    assert "pack-lsa-act-1987-s12" in ids  # free legal aid for a person in custody
    assert {"pack-bnss-2023-s47", "pack-bnss-2023-s478"} <= set(ids)
    assert "pack-patna-hc-kalam-ansari-2024-para9" in ids  # vehicle release on penalty


def test_follow_up_question_finds_law_through_the_earlier_turn(agent):
    alone = _prefetch(agent, "is taking people to jail for this okay?")
    with_context = _prefetch(agent, "is taking people to jail for this okay?", [BIHAR_ARREST])
    assert not [i for i in alone if "bihar" in i or "patna" in i]
    assert "pack-bihar-prohibition-excise-act-2016-s74" in with_context


def test_salary_question_gets_wage_law_without_unrelated_material(agent):
    ids = _prefetch(agent, "my company has not paid my salary for 2 months after I resigned")
    assert {"pack-code-on-wages-2019-s17", "pack-code-on-wages-2019-s45"} <= set(ids)
    assert not [i for i in ids if "bnss" in i or "bihar" in i or "hotel" in i]


def test_consumer_refund_keeps_its_certified_rules(agent):
    ids = _prefetch(
        agent, "Amazon picked up my returned item 12 days ago and closed my refund ticket."
    )
    assert "prop-consumer-ecommerce-grievance-r4" in ids


def test_claim_citing_a_pack_section_is_reviewable_not_blocked(agent):
    passage = next(p for p in _pack()["passages"] if p["passage_id"] == "pack-bnss-2023-s47")
    state = {"current_message": "Arrested.", "memory": {"facts": {}}, "passages": [passage]}
    claim = AnswerClaim(
        claim_id="c1",
        task_id="task-1",
        kind="legal",
        grounding="verified_legal_source",
        block_type="direct_answer",
        text="Under Section 47 of the BNSS, police must tell an arrested person the grounds.",
        evidence_ids=[passage["passage_id"]],
    )
    answer = AgentAnswer(central_question="q", tasks=[_task()], claims=[claim])
    blocked, _, pending = mechanical_checks(answer, EvidenceRegistry(state))
    assert not blocked and pending == ["c1"]


@pytest.mark.parametrize(
    ("message", "safety_category", "delivered", "expected"),
    [
        ("I want to end my life because of the debt calls", "self_harm", [], "handoff_crisis"),
        ("My husband is beating me right now", "domestic_violence", [], "handoff_safety"),
        ("Police entered our room and demand money now", "physical_safety", [], "handoff_liberty"),
        (BIHAR_ARREST, None, [], "handoff_liberty"),
        (BIHAR_ARREST, None, ["direct_answer", "human_handoff"], None),  # once per conversation
        ("Amazon has not refunded my returned phone", None, [], None),
    ],
)
def test_runtime_referral_matches_the_situation(message, safety_category, delivered, expected):
    from app.agent.blocks import handoff_template_id

    state = {
        "current_message": message,
        "safety_messages": [{"category": safety_category}] if safety_category else [],
        "context": {"prior_assistant_coverage": {"delivered_block_types": delivered}},
    }
    answer = AgentAnswer(central_question="q", tasks=[_task()], claims=[])
    assert handoff_template_id(answer, state) == expected


def test_primary_prompt_v2_structure_and_constraints():
    from typing import get_args

    from app.agent.contracts import BlockType, GroundingLabel

    prompt_path = Path(__file__).resolve().parents[1] / "app" / "prompts" / "primary.md"
    assert prompt_path.exists(), "primary.md prompt file is missing"
    text = prompt_path.read_text(encoding="utf-8")

    assert len(text) < 10500, f"Prompt too long: {len(text)} chars (limit 10500)"

    required_phrases = [
        "Work it out before you write",
        "what to do if it is refused or ignored",
        "next tier of the **same** route",
        "only when the user's message suggests a current risk",
        "matched to that route",
        "Before you finish",
        "phrased as questions for a lawyer",
        "knowledgeable friend",
        "never name sources inline",
    ]
    for phrase in required_phrases:
        assert phrase in text, f"Missing required phrase in primary.md: {phrase}"

    for bt in get_args(BlockType):
        assert bt in text, f"Missing BlockType '{bt}' in primary.md"

    for gl in get_args(GroundingLabel):
        assert gl in text, f"Missing GroundingLabel '{gl}' in primary.md"


def test_completeness_check_sends_unfinished_sentence_to_repair():
    state = {"current_message": "Deposit not returned.", "memory": {"facts": {}}, "passages": []}
    reg = EvidenceRegistry(state)

    # 1. Unfinished claim
    c_unfin = AnswerClaim(
        claim_id="c1",
        task_id="task-1",
        kind="practical",
        grounding="practical_precaution",
        block_type="immediate_actions",
        text="Keep the rent receipts and lease agreement",  # Missing full stop
    )
    ans1 = AgentAnswer(central_question="q", tasks=[_task()], claims=[c_unfin])
    blocked, approved, pending = mechanical_checks(ans1, reg)
    assert not blocked
    assert not approved
    assert "c1" in pending
    assert pending.get("c1") == "unfinished sentence"

    # 2. Finished claim passes to approved
    c_fin = AnswerClaim(
        claim_id="c2",
        task_id="task-1",
        kind="practical",
        grounding="practical_precaution",
        block_type="immediate_actions",
        text="Keep the rent receipts and lease agreement.",
    )
    ans2 = AgentAnswer(central_question="q", tasks=[_task()], claims=[c_fin])
    _, approved2, pending2 = mechanical_checks(ans2, reg)
    assert approved2 == {"c2": "risk_calibrated_consistency"}
    assert not pending2

    # 3. Markdown list passes
    c_list = AnswerClaim(
        claim_id="c3",
        task_id="task-1",
        kind="practical",
        grounding="practical_precaution",
        block_type="evidence_checklist",
        text="- Rent receipts\n- Landlord WhatsApp chats",
    )
    ans3 = AgentAnswer(central_question="q", tasks=[_task()], claims=[c_list])
    _, approved3, pending3 = mechanical_checks(ans3, reg)
    assert approved3 == {"c3": "risk_calibrated_consistency"}
    assert not pending3

    # 4. Markdown table passes
    c_table = AnswerClaim(
        claim_id="c4",
        task_id="task-1",
        kind="practical",
        grounding="practical_precaution",
        block_type="immediate_actions",
        text="| Item | Description |\n|---|---|\n| Receipts | Rent payment proof |",
    )
    ans4 = AgentAnswer(central_question="q", tasks=[_task()], claims=[c_table])
    _, approved4, pending4 = mechanical_checks(ans4, reg)
    assert approved4 == {"c4": "risk_calibrated_consistency"}
    assert not pending4

    # 5. Template claim is untouched (approved directly as template)
    c_tmpl = AnswerClaim(
        claim_id="c5",
        task_id="task-1",
        kind="template",
        template_id="handoff_liberty",
        text="",
    )
    ans5 = AgentAnswer(central_question="q", tasks=[_task()], claims=[c_tmpl])
    _, approved5, pending5 = mechanical_checks(ans5, reg)
    assert approved5 == {"c5": "approved_template"}
    assert not pending5
