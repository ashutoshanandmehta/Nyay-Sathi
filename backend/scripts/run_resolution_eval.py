"""One five-call live scenario using synthetic prior complaint history.

The earlier seven-call web regression plus this cap respect the configured twelve
request evaluation allowance for the current increment. No live service is mocked.
"""

import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.graph.workflow import AssistantGraph
from app.rag.retrieval import HybridRetriever
from app.resolution.journey import ComplaintJourneyService
from app.resolution.models import JourneyProposal
from app.schemas.models import CaseFact, CaseMemory
from app.services.context_builder import ContextBuilder


def main():
    settings = Settings()
    if (
        not settings.ai_configured
        or settings.live_eval_max_cases < 1
        or settings.live_eval_max_model_calls < 5
    ):
        print("Not run: credentials or evaluation budget missing.")
        return
    output = Path(__file__).parents[2] / "evals/raw_outputs/live-resolution-2026-11-06.jsonl"
    with tempfile.TemporaryDirectory(prefix="nyay-resolution-eval-") as folder:
        root = Path(folder)
        config = settings.model_copy(
            update={
                "database_path": root / "case.sqlite3",
                "checkpoint_path": root / "cp.sqlite3",
                "chroma_path": root / "chroma",
                "max_model_calls_per_turn": 5,
            }
        )
        retriever = HybridRetriever(config.model_copy(update={"openai_api_key": None}))
        graph = AssistantGraph(config, retriever)
        db = Database(config.database_path)
        owner = db.create_owner("synthetic")
        cid = db.create_conversation(owner, "en")["id"]
        previous = "I contacted Blinkit support about missing items. Ticket TEST-100. They promised a refund."
        memory = CaseMemory(
            domain="consumer",
            version=1,
            requested_remedy="Refund",
            facts={
                "consideration_paid": CaseFact(key="consideration_paid", value="1800"),
                "transaction_country": CaseFact(key="transaction_country", value="India"),
            },
        )
        ComplaintJourneyService().apply(
            memory.journey,
            [
                JourneyProposal(
                    event_type="complaint_submitted",
                    recipient="blinkit",
                    description="Reported complaint for missing items",
                    reference="TEST-100",
                ),
                JourneyProposal(
                    event_type="remedy_promised",
                    recipient="blinkit",
                    description="Refund promised; date not established",
                ),
            ],
            message_id="synthetic-prior",
            evidence=[],
        )
        message = "Write an email to Blinkit's grievance team using ticket TEST-100. They closed my ticket yesterday but I have not received the promised ₹1,800 refund. Keep it short and give me one lower-effort alternative."
        user = db.add_message(cid, "user", message, "synthetic-resolution-eval")
        current = {
            "owner_id": owner,
            "conversation_id": cid,
            "message_id": user["id"],
            "current_message": message,
            "memory": memory.model_dump(mode="json"),
            "context": ContextBuilder().build(
                current_message=message,
                memory=memory,
                summary="",
                recent_messages=[{"id": "synthetic-prior", "role": "user", "content": previous}],
            ),
            "language": "en",
            "passages": [],
            "request_plan": [],
            "request_coverage": [],
            "feedback_review": {},
            "revision_attempts": 0,
            "revision_succeeded": False,
            "model_calls": 0,
            "token_usage": {},
            "events": [],
        }
        started = time.perf_counter()
        try:
            result = graph.invoke(current, f"{owner}:{cid}")
            record = {
                "test_id": "live-prior-complaint-closure-adaptive-email",
                "input_messages": [previous, message],
                "attachment_ids": [],
                "expected_behaviour": [
                    "Use existing ticket",
                    "Do not restart complaint",
                    "Closed is not resolved",
                    "Clean email and useful alternative",
                    "No invented dates or addresses",
                ],
                "actual_outputs": {
                    "answer": result.get("response"),
                    "document": result.get("draft_content"),
                    "resolution_plan": result.get("resolution_plan"),
                    "draft_spec": result.get("draft_spec"),
                },
                "retrieved_passages": result.get("passages", []),
                "tool_events": result.get("events", []),
                "memory_updates": result.get("memory"),
                "case_version": result.get("memory", {}).get("version"),
                "verification_findings": result.get("verification", {}),
                "model_ids": [config.openai_chat_model, config.openai_review_model],
                "prompt_versions": ["v1-journey-resolution"],
                "corpus_version": retriever.corpus_version,
                "timestamp": datetime.now(UTC).isoformat(),
                "latency": round(time.perf_counter() - started, 3),
                "token_usage": result.get("token_usage", {}),
                "model_calls": result.get("model_calls"),
                "evaluation_status": "passed_automated_review"
                if result.get("verification", {}).get("passed") and result.get("draft_content")
                else "failed_or_limited",
                "reviewer_notes": "Synthetic seeded complaint history; actual live extraction/generation/review. No automated legal-correctness claim; lawyer review pending.",
            }
        except Exception as exc:
            record = {
                "test_id": "live-prior-complaint-closure-adaptive-email",
                "actual_outputs": {"error_type": type(exc).__name__},
                "evaluation_status": "execution_failed",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        finally:
            graph.connection.close()
        with output.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    key: record.get(key)
                    for key in ("evaluation_status", "latency", "model_calls", "token_usage")
                }
            )
        )


if __name__ == "__main__":
    main()
