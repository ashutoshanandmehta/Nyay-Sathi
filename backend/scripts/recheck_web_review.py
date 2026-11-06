"""Two-call live recheck of the previous fetched evidence with policy grounding.

This deliberately reuses actual recorded public passages; it is not another full
search journey. No model/provider is mocked.
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
from app.schemas.models import CaseMemory
from app.services.context_builder import ContextBuilder


def main():
    root = Path(__file__).parents[2]
    previous = json.loads(
        (root / "evals/raw_outputs/live-web-research-2026-11-06.jsonl").read_text().splitlines()[-1]
    )
    config = Settings()
    from scripts.live_guard import require_live_budget
    require_live_budget(config, minimum_requests=2)
    if not config.ai_configured or config.live_eval_max_model_calls < 2:
        print("Not run: configuration/budget missing")
        return
    with tempfile.TemporaryDirectory(prefix="nyay-web-review-") as folder:
        config = config.model_copy(
            update={
                "database_path": Path(folder) / "app.sqlite3",
                "checkpoint_path": Path(folder) / "cp.sqlite3",
                "max_model_calls_per_turn": 2,
            }
        )
        db = Database(config.database_path)
        owner = db.create_owner("synthetic")
        cid = db.create_conversation(owner, "en")["id"]
        retriever = HybridRetriever(config.model_copy(update={"openai_api_key": None}))
        graph = AssistantGraph(config, retriever)
        memory = CaseMemory.model_validate(previous["memory_updates"])
        message = previous["input_messages"][-1]
        state = {
            "owner_id": owner,
            "conversation_id": cid,
            "message_id": "web-review-recheck",
            "current_message": message,
            "context": ContextBuilder().build(
                current_message=message, memory=memory, summary="", recent_messages=[]
            ),
            "memory": memory.model_dump(mode="json"),
            "language": "en",
            "request_plan": [
                {
                    "request_id": "request-1",
                    "kind": "options",
                    "request_text": "Explain current NCH complaint procedure and information to prepare",
                    "requires_legal_retrieval": True,
                }
            ],
            "passages": previous["retrieved_passages"],
            "research_plan": previous["actual_outputs"]["research_plan"],
            "research_status": "fetched_pending_review",
            "model_calls": 0,
            "token_usage": {},
            "needs_retrieval": True,
            "revision_succeeded": False,
            "scope": "consumer",
            "intent": "options",
        }
        started = time.perf_counter()
        try:
            state.update(graph.plan_resolution(state))
            state.update(graph.respond(state))
            state.update(graph.review_response(state))
            result = graph.verify(state)
            record = {
                "test_id": "live-fetched-web-review-recheck",
                "input_messages": [message],
                "attachment_ids": [],
                "expected_behaviour": [
                    "Use actual previously fetched passages",
                    "Ground route definitions",
                    "No fabricated current procedure",
                ],
                "actual_outputs": {"answer": result.get("response", state["response"])},
                "retrieved_passages": state["passages"],
                "tool_events": state.get("events", []),
                "memory_updates": state["memory"],
                "case_version": memory.version,
                "verification_findings": result["verification"],
                "model_ids": [config.openai_chat_model, config.openai_review_model],
                "prompt_versions": ["v1-journey-policy-grounding"],
                "corpus_version": retriever.corpus_version,
                "timestamp": datetime.now(UTC).isoformat(),
                "latency": round(time.perf_counter() - started, 3),
                "token_usage": state["token_usage"],
                "model_calls": state["model_calls"],
                "evaluation_status": "passed_automated_review"
                if result["verification"]["passed"]
                else "failed_or_limited",
                "reviewer_notes": "Actual generation/review using previously fetched live sources plus registered primary policy bases. Not a new complete search journey. Lawyer review pending.",
            }
        finally:
            graph.connection.close()
    with (root / "evals/raw_outputs/live-web-review-recheck-2026-11-06.jsonl").open("a") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {key: record.get(key) for key in ("evaluation_status", "latency", "model_calls")}
        )
    )


if __name__ == "__main__":
    main()
