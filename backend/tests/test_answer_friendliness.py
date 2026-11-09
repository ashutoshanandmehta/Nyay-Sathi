"""Answers read like help, not a legal file: no echoed IDs, a lawyer only when one is needed, no
emergency banner for something already over, and the rule that matters is found.

Offline: scripted model outputs and the local index only. Shapes come from a real Patna hotel
conversation where a couple paid police ₹5,000 to leave and got raw IDs, a danger banner, a
lawyer section that was really an offer of help, and no word on the 7-day reporting rule.
"""

import pytest

from app.agent.blocks import format_claim_text
from app.agent.contracts import AgentAnswer, AnswerClaim
from app.agent.safety import detect_urgent_category
from tests.conftest import create_case
from tests.test_answer_quality import (
    _fixture_passage,
    _post,
    _prefetch,
    _research_with,
    _task,
    agent,  # noqa: F401  (module fixture)
)
from tests.test_primary_agent import ScriptedProvider, install
from tests.test_repair_and_drafts import _review, _verdict

PAID_POLICE = (
    "The manager called two police officers, who entered our room and started asking personal "
    "questions. They were threatening to call our parents and register a case against us. One "
    "officer even said we could settle the matter by paying ₹5,000. We paid them 5,000 to escape."
)
HOTEL = "We are both 20 and booked an OYO in Patna. Is it illegal for an unmarried couple to stay?"


def _claim(claim_id, block_type, text, **fields):
    return AnswerClaim(
        **{
            "claim_id": claim_id,
            "task_id": "task-1",
            "kind": "practical",
            "grounding": "practical_precaution",
            "block_type": block_type,
            "text": text,
            **fields,
        }
    )


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("Not a crime by itself. [1][2]", "Not a crime by itself."),
        ("Note what was said. [segment:seg-1]", "Note what was said."),
        ("Report it. [prop-urgent-pca-1988-bribe-demand-s7]", "Report it."),
        ("Write to them [web-fc2f93ea-official-webpage-0-975d] today.", "Write to them today."),
        ("On [Date], at [Police Station].", "On [Date], at [Police Station]."),
    ],
)
def test_ids_and_model_numbers_never_reach_the_reader(raw, shown):
    assert format_claim_text(_claim("c", "immediate_actions", raw), "en") == shown


def test_an_offer_of_help_is_not_shown_as_the_lawyer_section(client, isolated_app):
    cid = create_case(client)
    first = AgentAnswer(
        central_question="q",
        tasks=[_task(domain="consumer")],
        claims=[
            _claim("short", "direct_answer", "No, staying together is not a crime by itself."),
            _claim("keep", "immediate_actions", "Keep your booking confirmation and payment proof."),
            _claim(
                "offer",
                "human_handoff",
                "If you share the booking terms, I can help you draft a message to OYO.",
            ),
        ],
    )
    provider = ScriptedProvider(first, _review(_verdict("short"), _verdict("offer")))
    install(isolated_app, provider, _research_with(_fixture_passage()))

    message = _post(client, cid, HOTEL).json()["assistant_message"]

    assert "When a lawyer would help" not in message["content"]
    assert "I can help you draft a message to OYO." in message["content"]
    blocks = message["metadata"]["resolution_blocks"]
    assert "human_handoff" not in [b["block_type"] for b in blocks]  # so no bundle button either
    assert "\n---\n" not in message["content"]  # one flowing message, not ruled-off forms


def test_a_real_lawyer_handoff_keeps_its_section(client, isolated_app):
    cid = create_case(client)
    first = AgentAnswer(
        central_question="q",
        tasks=[_task()],
        claims=[
            _claim("short", "direct_answer", "Your brother can apply for bail."),
            _claim(
                "lawyer",
                "human_handoff",
                "A local criminal lawyer can apply for bail; free legal aid may be available.",
            ),
        ],
    )
    provider = ScriptedProvider(first, _review(_verdict("short"), _verdict("lawyer")))
    install(isolated_app, provider, _research_with(_fixture_passage()))

    message = _post(client, cid, "My brother is in jail, what now?").json()["assistant_message"]

    assert "### When a lawyer would help" in message["content"]


@pytest.mark.parametrize(
    ("message", "category"),
    [
        (PAID_POLICE, None),  # already over: no "if you are in immediate danger" banner
        ("Two police officers entered our room and are demanding 5000 right now", "physical_safety"),
        ("We escaped but the officers keep calling and threatening us", "physical_safety"),
        ("Police detained my brother yesterday and demand a bribe to release him", "physical_safety"),
    ],
)
def test_the_danger_banner_is_for_danger_that_is_still_happening(message, category):
    assert detect_urgent_category(message) == category


def test_paying_police_brings_the_seven_day_reporting_rule_despite_a_louder_topic(agent):  # noqa: F811
    ids = _prefetch(agent, PAID_POLICE, [HOTEL])
    assert "prop-urgent-pca-1988-compelled-reporting-s8" in ids


def test_prompts_keep_lawyers_for_real_need_and_ids_out_of_text():
    from pathlib import Path

    prompts = Path(__file__).resolve().parents[1] / "app" / "prompts"
    primary = (prompts / "primary.md").read_text()
    review = (prompts / "primary-review.md").read_text()
    assert "only when a lawyer would really change the outcome" in primary
    assert "offer of more help goes in the last `immediate_actions` claim" in primary
    assert "never in `claim.text`" in primary
    assert "a missing lawyer referral is not a defect" in review
