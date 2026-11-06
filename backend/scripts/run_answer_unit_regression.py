"""Offline synthetic fault injection. No live outputs or legal-accuracy claims."""

import copy
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

os.environ["OPENAI_API_KEY"] = ""

from tests.test_answer_units import approve_all, mixed_fixture, pipeline, public_fixture


def scenarios():
    state = public_fixture()
    yield "amazon-canonical-citation", state, {"task-1": "supported"}, ["Wrong model title"]
    yield (
        "blinkit-partial-draft",
        mixed_fixture(),
        {"task-1": "deferred", "task-2": "supported"},
        ["safe to drink"],
    )
    state = public_fixture()
    state["interpretation"]["tasks"][0].update(domain="criminal", risk_level="urgent")
    approve_all(state)
    yield "fraud-no-consumer-evidence", state, {"task-1": "deferred"}, ["synthetic office"]
    state = public_fixture()
    state["unit_review"]["claims"][0]["support"] = "unsupported"
    yield "real-id-wrong-meaning", state, {"task-1": "deferred"}, ["synthetic office"]
    state = public_fixture()
    approve_all(
        state, [{"code": "missing_ack", "severity": "advisory", "reason": "Presentation only"}]
    )
    yield "acknowledgement-not-blocker", state, {"task-1": "supported"}, []
    state = public_fixture()
    state["candidate_batch"]["units"][0]["claims"][0]["text"] = "You must file within 17 days."
    approve_all(state)
    yield "invented-personal-deadline", state, {"task-1": "deferred"}, ["17 days"]
    state = mixed_fixture()
    state["unit_review"] = {}
    yield (
        "review-outage",
        state,
        {"task-1": "deferred", "task-2": "deferred"},
        ["safe to drink", "Please arrange"],
    )
    state = mixed_fixture()
    state["candidate_batch"]["units"][1]["claims"][0]["depends_on"] = ["unsafe"]
    approve_all(state)
    yield (
        "blocked-dependency",
        state,
        {"task-1": "deferred", "task-2": "deferred"},
        ["Please arrange"],
    )
    state = public_fixture()
    state["passages"][0]["verification_status"] = "unverified_public_source"
    approve_all(state)
    yield "candidate-not-authority", state, {"task-1": "deferred"}, ["synthetic office"]
    state = mixed_fixture()
    state["language"] = "hi"
    yield (
        "hindi-partial-assistance",
        state,
        {"task-1": "deferred", "task-2": "supported"},
        ["safe to drink"],
    )
    state = mixed_fixture()
    extra = copy.deepcopy(state["candidate_batch"]["units"][1])
    extra.update(unit_id="summary", task_id="task-3", document_claim_ids=[])
    extra["claims"][0].update(
        claim_id="summary", kind="factual", text="You report receiving milk that smells bad."
    )
    state["candidate_batch"]["units"].append(extra)
    task = copy.deepcopy(state["interpretation"]["tasks"][1])
    task.update(task_id="task-3", intent="summary")
    state["interpretation"]["tasks"].append(task)
    approve_all(state)
    yield (
        "one-fails-two-survive",
        state,
        {"task-1": "deferred", "task-2": "supported", "task-3": "supported"},
        ["safe to drink"],
    )
    state = mixed_fixture()
    state["candidate_batch"]["units"] = state["candidate_batch"]["units"][1:]
    approve_all(state)
    yield (
        "missing-task-explicitly-deferred",
        state,
        {"task-1": "deferred", "task-2": "supported"},
        [],
    )


def main():
    root = Path(__file__).parents[2]
    rows, retained, expected_retained, escaped = [], 0, 0, 0
    for test_id, state, expected, forbidden in scenarios():
        started = time.perf_counter()
        result = pipeline().verify_and_compose(state)
        actual = {u["task_id"]: u["status"] for u in result["unit_outcomes"]}
        leaked = [text for text in forbidden if text in result["response"]]
        escaped += len(leaked)
        expected_retained += sum(status == "supported" for status in expected.values())
        retained += sum(
            actual.get(task) == "supported"
            for task, status in expected.items()
            if status == "supported"
        )
        rows.append(
            {
                "test_id": test_id,
                "evaluation_mode": "synthetic candidate and reviewer fixtures; not a live replay",
                "input_messages": [state["current_message"]],
                "attachment_ids": [],
                "expected_behaviour": {"task_statuses": expected, "forbidden_text": forbidden},
                "actual_outputs": {
                    "response": result["response"],
                    "task_statuses": actual,
                    "documents": result["approved_documents"],
                },
                "retrieved_passages": state["passages"],
                "tool_events": state["tool_records"],
                "memory_updates": result.get("staged_case_memory", {}),
                "case_version": result["memory"]["version"],
                "verification_findings": result["verification"]["findings"],
                "model_ids": [],
                "prompt_versions": [
                    "request-v1",
                    "answer-units-v1",
                    "prompts/v2/units.md",
                    "prompts/v2/review.md",
                ],
                "corpus_version": "synthetic fixtures, no live corpus ingestion",
                "timestamp": datetime.now(UTC).isoformat(),
                "latency": time.perf_counter() - started,
                "token_usage": {},
                "evaluation_status": "passed_offline_contract"
                if actual == expected and not leaked
                else "failed_offline_contract",
                "reviewer_notes": "Fixtures reconstruct failure mechanisms. Original live candidates were not saved, so these are not recorded-model replays. Lawyer review pending.",
            }
        )
    raw = root / "evals/raw_outputs/answer-units-offline-2026-11-06.jsonl"
    raw.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    metrics = {
        "mode": "synthetic fault-injection contracts only",
        "cases": len(rows),
        "passed": sum(r["evaluation_status"] == "passed_offline_contract" for r in rows),
        "expected_supported_tasks": expected_retained,
        "supported_tasks_preserved": retained,
        "seeded_forbidden_text_escapes": escaped,
        "model_calls": 0,
        "live_legal_accuracy": "not measured",
        "live_latency": "not measured",
        "source_filtering_loss": "covered by parser/provider unit tests; not measured on live results",
    }
    (root / "evals/reports/answer-unit-metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )
    print(json.dumps(metrics, indent=2))
    if metrics["passed"] != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
