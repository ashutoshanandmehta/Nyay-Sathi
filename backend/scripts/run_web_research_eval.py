"""One budgeted live graph journey with an intentionally empty local corpus.

All planner, search, fetch, generation and review calls are live. Only the local
corpus is deliberately empty to exercise fallback. No personal records are used.
"""

import json
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.graph.workflow import AssistantGraph
from app.rag.retrieval import HybridRetriever
from app.schemas.models import CaseMemory
from app.services.context_builder import ContextBuilder


def main():
    config = Settings()
    if (
        not config.ai_configured
        or config.live_eval_max_cases < 1
        or config.live_eval_max_model_calls < 8
    ):
        print("Not run: missing credentials or fewer than eight model calls permitted.")
        return
    output = Path(__file__).parents[2] / "evals/raw_outputs/live-web-research-2026-11-06.jsonl"
    with tempfile.TemporaryDirectory(prefix="nyay-web-eval-") as directory:
        root = Path(directory)
        config = config.model_copy(
            update={
                "database_path": root / "app.sqlite3",
                "checkpoint_path": root / "cp.sqlite3",
                "chroma_path": root / "chroma",
                "max_model_calls_per_turn": 8,
            }
        )
        # Create a real empty retriever; no external-service doubles are used.
        retriever = HybridRetriever(config.model_copy(update={"openai_api_key": None}))
        retriever.passages = []
        retriever.bm25 = None
        graph = AssistantGraph(config, retriever)
        db = Database(config.database_path)
        owner = db.create_owner("synthetic-evaluation-owner")
        cid = db.create_conversation(owner, "en")["id"]
        message = "An online seller refuses my promised refund. What is the current National Consumer Helpline complaint procedure and what information should I prepare?"
        user = db.add_message(cid, "user", message, str(uuid.uuid4()))
        memory = CaseMemory()
        state = {
            "owner_id": owner,
            "conversation_id": cid,
            "message_id": user["id"],
            "current_message": message,
            "language": "en",
            "context": ContextBuilder().build(
                current_message=message, memory=memory, summary="", recent_messages=[user]
            ),
            "memory": memory.model_dump(mode="json"),
            "summary": "",
            "passages": [],
            "research_plan": {},
            "research_status": "not_required",
            "request_plan": [],
            "request_coverage": [],
            "feedback_review": {},
            "events": [],
            "model_calls": 0,
            "token_usage": {},
            "revision_attempts": 0,
            "revision_succeeded": False,
        }
        started = time.perf_counter()
        try:
            result = graph.invoke(state, f"{owner}:{cid}")
            record = {
                "test_id": "live-empty-corpus-consumer-procedure",
                "input_messages": [message],
                "attachment_ids": [],
                "expected_behaviour": [
                    "Detect missing public procedure",
                    "Generate sanitised query",
                    "Fetch official passages",
                    "Review before display",
                ],
                "actual_outputs": {
                    "answer": result.get("response"),
                    "research_plan": result.get("research_plan"),
                    "research_status": result.get("research_status"),
                },
                "retrieved_passages": result.get("passages", []),
                "tool_events": result.get("events", []),
                "memory_updates": result.get("memory"),
                "case_version": result.get("memory", {}).get("version"),
                "verification_findings": result.get("verification", {}),
                "model_ids": [
                    config.openai_chat_model,
                    config.openai_review_model,
                    config.openai_web_search_model,
                ],
                "prompt_versions": ["v1-research"],
                "corpus_version": "deliberately-empty-live-evaluation",
                "timestamp": datetime.now(UTC).isoformat(),
                "latency": round(time.perf_counter() - started, 3),
                "token_usage": result.get("token_usage", {}),
                "model_calls": result.get("model_calls"),
                "evaluation_status": "passed_observable_workflow"
                if result.get("verification", {}).get("passed")
                and any(p.get("origin") == "web" for p in result.get("passages", []))
                else "failed_or_limited",
                "reviewer_notes": "Actual live services; deliberately empty local corpus. Automated review is not legal validation; lawyer review pending.",
            }
        except Exception as exc:
            record = {
                "test_id": "live-empty-corpus-consumer-procedure",
                "input_messages": [message],
                "actual_outputs": {"error_type": type(exc).__name__},
                "evaluation_status": "execution_failed",
                "latency": round(time.perf_counter() - started, 3),
                "timestamp": datetime.now(UTC).isoformat(),
                "reviewer_notes": "No successful integration claim.",
            }
        finally:
            graph.connection.close()
        with output.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    k: record.get(k)
                    for k in ("evaluation_status", "latency", "model_calls", "token_usage")
                }
            )
        )


if __name__ == "__main__":
    main()
