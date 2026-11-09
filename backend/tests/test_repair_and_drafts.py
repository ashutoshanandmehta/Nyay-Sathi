"""Repair sees every unapproved claim, stops when it changes nothing, and re-reviews only edits;
requested drafts reach review; multi-issue answers share one set of headings.

Offline: scripted model outputs only. Shapes come from a real Nalanda land/threat conversation
where a police-complaint template vanished and two empty repair rounds re-ran identical reviews.
"""

import json

from app.agent.blocks import DRAFT_WITHHELD_NOTE
from app.agent.contracts import (
    AgentAnswer,
    AgentReview,
    AnswerClaim,
    ClaimVerdict,
    RepairPatch,
)
from app.agent.verification import mechanical_checks
from app.answers.evidence import EvidenceRegistry
from tests.conftest import create_case
from tests.test_answer_quality import _fixture_passage, _post, _research_with, _task
from tests.test_primary_agent import ScriptedProvider, install

THREAT = "My uncle sends threatening WhatsApp messages about our land. Make a template for the police."


class RecordingProvider(ScriptedProvider):
    """Also keeps each call's system instructions."""

    def __init__(self, *outputs):
        super().__init__(*outputs)
        self.instructions = []

    def complete(self, items, instructions, budget, **kwargs):
        self.instructions.append(instructions)
        return super().complete(items, instructions, budget, **kwargs)


def _payload(provider, index):
    return json.loads(provider.requests[index][0][0]["content"])


def _claim(claim_id, **fields):
    return AnswerClaim(**{"claim_id": claim_id, "task_id": "task-1", **fields})


def _verdict(claim_id, support="supported", reason="ok"):
    return ClaimVerdict(
        claim_id=claim_id, support=support, reason=reason, requires_public_evidence=False
    )


def _review(*verdicts):
    return AgentReview(
        claims=list(verdicts), primary_question_answered=True, next_action_useful=True
    )


def _law(claim_id, text, evidence=("fix-law",)):
    return _claim(
        claim_id,
        kind="procedure",
        block_type="recommended_route",
        grounding="verified_legal_source",
        text=text,
        evidence_ids=list(evidence),
    )


def test_a_draft_without_cited_facts_goes_to_review_instead_of_vanishing():
    state = {"current_message": THREAT, "memory": {"facts": {}}, "passages": []}
    draft = _claim(
        "doc",
        kind="document",
        block_type="document",
        grounding="practical_precaution",
        in_document=True,
        text="To,\nThe Station House Officer,\n[Police Station]\n\nI, [Name], report messages sent on [Date].",
    )
    legal = _claim("law", kind="legal", grounding="verified_legal_source", text="The police must act.")
    blocked, approved, pending = mechanical_checks(
        AgentAnswer(central_question="q", tasks=[_task(intent="draft")], claims=[draft, legal]),
        EvidenceRegistry(state),
    )
    assert pending.get("doc") == "draft without cited facts"
    assert "doc" not in blocked and "doc" not in approved
    assert blocked["law"] == "missing_public_evidence"  # law without a source is still blocked


def test_repair_gets_blocked_claims_with_reasons_and_only_edits_are_re_reviewed(client, isolated_app):
    cid = create_case(client)
    first = AgentAnswer(
        central_question="q",
        tasks=[_task()],
        claims=[
            _law("route", "Your brother must be told why he was arrested."),
            _law("ghost", "A ghost section applies here.", evidence=("no-such-passage",)),
        ],
    )
    patch = RepairPatch(
        replacements=[_law("ghost", "Ask the police to tell him the grounds of arrest.")]
    )
    provider = RecordingProvider(
        first, _review(_verdict("route")), patch, _review(_verdict("ghost"))
    )
    runner = install(isolated_app, provider, _research_with(_fixture_passage()))
    runner.settings.agent_max_rounds, runner.settings.agent_max_repairs = 5, 2

    meta = _post(client, cid, "Why was my brother arrested?").json()["assistant_message"]

    repair = _payload(provider, 2)
    assert [p["claim"]["claim_id"] for p in repair["claims_to_repair"]] == ["ghost"]
    assert repair["claims_to_repair"][0]["problem"] == "unknown_evidence"
    assert [c["claim_id"] for c in repair["other_claims"]] == ["route"]
    # The repair model works under the same rules as the first answer.
    assert provider.instructions[2] == runner.prompt
    # The supported claim is not reviewed again.
    assert _payload(provider, 3)["pending_claim_ids"] == ["ghost"]
    assert meta["metadata"]["publication_status"] == "supported"
    assert "Ask the police to tell him the grounds of arrest." in meta["content"]


def test_reviewer_and_repair_do_not_receive_a_second_full_copy_of_the_evidence(client, isolated_app):
    cid = create_case(client)
    unrelated = _fixture_passage("unrelated-law")
    first = AgentAnswer(
        central_question="q", tasks=[_task()], claims=[_law("route", "Unverified route.")]
    )
    patch = RepairPatch(replacements=[_law("route", "Ask for the grounds of arrest.")])
    provider = ScriptedProvider(
        first,
        _review(_verdict("route", "unsupported", "too broad")),
        patch,
        _review(_verdict("route")),
    )
    runner = install(isolated_app, provider, _research_with(_fixture_passage(), unrelated))
    runner.settings.agent_max_rounds, runner.settings.agent_max_repairs = 5, 2
    _post(client, cid, "Why was my brother arrested?")

    review, repair = _payload(provider, 1), _payload(provider, 2)
    for payload in (review, repair):
        assert "evidence" not in payload["context"]
        assert "templates" not in payload["context"]
    assert "draft" not in review  # claims are sent once
    assert [e["evidence_id"] for e in review["evidence"]] == ["fix-law"]
    assert "unrelated-law" not in [e["evidence_id"] for e in repair["evidence"]]
    assert "unrelated-law" in [e["evidence_id"] for e in repair["other_evidence_index"]]
    assert "previous_answer" not in repair and "review" not in repair


def test_an_empty_repair_patch_stops_the_loop_without_another_review(client, isolated_app):
    cid = create_case(client)
    first = AgentAnswer(
        central_question="q", tasks=[_task()], claims=[_law("route", "Unverified route.")]
    )
    provider = ScriptedProvider(
        first, _review(_verdict("route", "unsupported", "not in source")), RepairPatch()
    )
    runner = install(isolated_app, provider, _research_with(_fixture_passage()))
    runner.settings.agent_max_rounds, runner.settings.agent_max_repairs = 5, 2

    meta = _post(client, cid, "Why was my brother arrested?").json()["assistant_message"]

    assert len(provider.requests) == 3  # answer, review, repair; no identical re-review
    assert meta["metadata"]["publication_status"] == "partial"
    assert any(
        e.get("result") == "Repair found nothing it could fix safely"
        for e in meta["metadata"]["events"]
    )


def test_two_issues_share_one_set_of_headings_in_task_order(client, isolated_app):
    cid = create_case(client)
    land = _task(task_id="task-2", title="Land", domain="other_legal")

    def route(claim_id, task_id, text):
        return AnswerClaim(
            claim_id=claim_id,
            task_id=task_id,
            kind="practical",
            block_type="recommended_route",
            grounding="practical_precaution",
            text=text,
        )

    first = AgentAnswer(
        central_question="q",
        tasks=[_task(), land],
        claims=[
            route("police", "task-1", "For the threats: report them at the police station."),
            _claim(
                "ask",
                kind="question",
                block_type="question",
                grounding="requires_confirmation",
                text="Do the messages threaten physical harm?",
            ),
            route("records", "task-2", "For the land records: ask the Circle Officer about mutation."),
        ],
    )
    provider = ScriptedProvider(first, _review(_verdict("police"), _verdict("records")))
    install(isolated_app, provider, _research_with(_fixture_passage()))

    content = _post(client, cid, THREAT).json()["assistant_message"]["content"]

    assert content.count("### What I'd suggest") == 1
    assert content.index("For the threats:") < content.index("For the land records:")
    assert content.index("For the land records:") < content.index("### One thing that would help me")


def test_a_draft_with_a_rejected_part_is_withheld_with_an_honest_note(client, isolated_app):
    cid = create_case(client)

    def part(claim_id, text):
        return _claim(
            claim_id,
            kind="document",
            block_type="document",
            grounding="practical_precaution",
            in_document=True,
            evidence_ids=["segment:seg-1"],
            text=text,
        )

    first = AgentAnswer(
        central_question="q",
        tasks=[_task(intent="draft")],
        claims=[
            _claim(
                "intro",
                kind="practical",
                block_type="direct_answer",
                grounding="practical_precaution",
                text="Your father can adapt the draft to what happened.",
            ),
            part("head", "To,\nThe Station House Officer,\n[Police Station]"),
            part("body", "This is an offence punishable with seven years in jail."),
        ],
    )
    provider = ScriptedProvider(
        first, _review(_verdict("head"), _verdict("body", "unsupported", "invents a penalty"))
    )
    runner = install(isolated_app, provider, _research_with(_fixture_passage()))
    runner.settings.agent_max_repairs = 0

    content = _post(client, cid, THREAT).json()["assistant_message"]["content"]

    assert DRAFT_WITHHELD_NOTE["en"] in content
    assert "The Station House Officer" not in content  # no half-draft
    assert client.get(f"/api/conversations/{cid}").json()["drafts"] == []
