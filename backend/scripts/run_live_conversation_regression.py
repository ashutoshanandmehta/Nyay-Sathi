"""Run one budgeted synthetic conversation against the local live API."""

import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import Settings

ROOT = Path(__file__).parents[2]
MESSAGE = (
    "I ordered a mixer grinder from HomeStore for ₹3,200. "
    "Delivery was promised by 12 October. Tracking says delivered, but I did not receive it. "
    "No one at home or reception received it. The courier has not shown a delivery photo or OTP record. "
    "What evidence should I collect? Prepare a factual complaint summary."
)


def main() -> int:
    settings = Settings()
    from scripts.live_guard import require_live_budget
    require_live_budget(settings)
    started = time.perf_counter()
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=180) as client:
        bootstrap = client.get("/api/bootstrap")
        bootstrap.raise_for_status()
        client.headers["X-CSRF-Token"] = client.cookies["nyay_csrf"]
        conversation = client.post("/api/conversations", json={"language": "en"})
        conversation.raise_for_status()
        cid = conversation.json()["id"]
        try:
            turn = client.post(
                f"/api/conversations/{cid}/turns",
                json={
                    "content": MESSAGE,
                    "request_id": f"live-regression-{uuid.uuid4()}",
                    "language": "en",
                    "attachment_ids": [],
                },
            )
            turn.raise_for_status()
            payload = turn.json()
            detail = client.get(f"/api/conversations/{cid}").json()
            answer = payload["assistant_message"]["content"]
            metadata = payload["assistant_message"]["metadata"]
            checks = {
                "starts_with_acknowledgement_before_heading": not answer.lstrip().startswith("#"),
                "mentions_evidence": bool(re.search(r"evidence|invoice|tracking", answer, re.I)),
                "contains_factual_summary": bool(
                    re.search(r"factual summary|summary", answer, re.I)
                ),
                "does_not_render_internal_keys": not any(
                    key in answer
                    for key in ("request_coverage", "confirmed_and_reported_facts", "graph_state")
                ),
                "does_not_invent_year": not bool(re.search(r"12 October 20\d{2}", answer, re.I)),
                "does_not_treat_otp_gap_as_proof": not bool(
                    re.search(r"(?:absence|lack|no).{0,30}otp.{0,30}proves?", answer, re.I)
                ),
                "asks_at_most_one_question": answer.count("?") <= 1,
                "asks_desired_resolution": bool(
                    re.search(
                        r"(?:what|which).{0,30}(?:resolution|outcome)|would you (?:like|prefer).{0,40}(?:refund|replacement|delivery)",
                        answer.rsplit("\n", 2)[-1],
                        re.I,
                    )
                ),
                "verification_passed": bool(payload.get("verification", {}).get("passed")),
            }
            health = client.get("/api/health").json()
            record = {
                "test_id": "live-conversation-multi-request-regression",
                "input_messages": [MESSAGE],
                "attachment_ids": [],
                "expected_behaviour": [
                    "brief acknowledgement",
                    "practical evidence checklist",
                    "provisional factual summary",
                    "no missing-year inference",
                    "one desired-resolution question",
                    "no raw internal schema",
                ],
                "actual_outputs": {"assistant": answer, "objective_checks": checks},
                "retrieved_passages": metadata.get("sources", []),
                "tool_events": metadata.get("events", []),
                "memory_updates": detail["case_memory"],
                "case_version": payload["case_version"],
                "verification_findings": payload.get("verification", {}),
                "model_ids": [settings.openai_chat_model, settings.openai_review_model],
                "prompt_versions": ["v1-conversation-feedback"],
                "corpus_version": health["corpus_version"],
                "timestamp": datetime.now(UTC).isoformat(),
                "latency": round(time.perf_counter() - started, 3),
                "token_usage": payload.get("token_usage", {}),
                "evaluation_status": "passed_objective_checks"
                if all(checks.values())
                else "failed_objective_checks",
                "reviewer_notes": "Automated checks do not establish legal correctness; lawyer review remains pending.",
            }
            output = ROOT / "evals" / "raw_outputs" / "live-conversation-2026-11-05.jsonl"
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("a") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                json.dumps(
                    {
                        "output": str(output),
                        "status": record["evaluation_status"],
                        "checks": checks,
                        "latency": record["latency"],
                        "token_usage": record["token_usage"],
                    }
                )
            )
            return 0 if all(checks.values()) else 1
        finally:
            client.delete(f"/api/conversations/{cid}")


if __name__ == "__main__":
    raise SystemExit(main())
