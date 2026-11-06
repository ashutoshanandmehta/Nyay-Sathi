"""Follow-up to the recorded live search: fetch its returned URLs and spend two model calls on generation/review."""

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
from app.services.web_research import (
    EvidenceSufficiencyAssessor,
    QueryIntent,
    ResearchRepository,
    SafeSourceFetcher,
)


def main():
    config = Settings()
    from scripts.live_guard import require_live_budget
    require_live_budget(config, minimum_requests=2)
    root = Path(__file__).parents[2]
    previous = json.loads(
        (root / "evals/raw_outputs/live-web-research-2026-11-06.jsonl").read_text().splitlines()[0]
    )
    # Actual URLs returned by the successful preceding live search diagnostic.
    urls = [
        "https://consumerhelpline.gov.in/public/contact",
        "https://consumerhelpline.gov.in/apps/consumerapp/",
        "https://consumerhelpline.gov.in/apps/umang/?trk=public_post_comment-text",
    ]
    record = {
        "test_id": "live-discovered-source-generation-review",
        "timestamp": datetime.now(UTC).isoformat(),
        "input_messages": previous["input_messages"],
        "attachment_ids": [],
        "expected_behaviour": [
            "Fetch previously discovered official sources",
            "Use supporting excerpts only",
            "Independent review",
        ],
        "search_source": "URLs from preceding actual live search; no new search or model-generated fixture",
        "tool_events": [],
    }
    if not config.ai_configured or config.live_eval_max_model_calls < 2:
        print("Not run: credentials or budget missing")
        return
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="nyay-discovery-check-") as directory:
        temp = Path(directory)
        config = config.model_copy(
            update={
                "database_path": temp / "app.sqlite3",
                "checkpoint_path": temp / "cp.sqlite3",
                "max_model_calls_per_turn": 2,
            }
        )
        db = Database(config.database_path)
        owner = db.create_owner("synthetic")
        cid = db.create_conversation(owner, "en")["id"]
        repository = ResearchRepository(config)
        passages = []
        for url in urls:
            try:
                source = SafeSourceFetcher(config).read(
                    {"url": url, "title": "National Consumer Helpline official guidance"}, 10
                )
                repository.save(owner, cid, "follow-up-live", source)
                selected = EvidenceSufficiencyAssessor.select(
                    source["passages"], [QueryIntent(topic="grievance", angle="current_procedure")]
                )
                passages.extend(selected)
                record["tool_events"].append(
                    {
                        "url": url,
                        "status": "fetched",
                        "passages": len(selected),
                        "content_hash": source["hash"],
                    }
                )
            except Exception as exc:
                record["tool_events"].append(
                    {"url": url, "status": "fetch_failed", "error_type": type(exc).__name__}
                )
        retriever = HybridRetriever(config.model_copy(update={"openai_api_key": None}))
        graph = AssistantGraph(config, retriever)
        message = previous["input_messages"][0]
        memory = CaseMemory.model_validate(previous["memory_updates"])
        state = {
            "owner_id": owner,
            "conversation_id": cid,
            "message_id": "follow-up-live",
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
            "passages": passages[:5],
            "research_plan": previous["actual_outputs"]["research_plan"],
            "research_status": "fetched_pending_review" if passages else "insufficient_web_support",
            "model_calls": 0,
            "token_usage": {},
            "needs_retrieval": True,
            "revision_succeeded": False,
        }
        try:
            state.update(graph.respond(state))
            state.update(graph.review_response(state))
            result = graph.verify(state)
            record.update(
                {
                    "actual_outputs": {"answer": result.get("response", state.get("response"))},
                    "retrieved_passages": state["passages"],
                    "memory_updates": state["memory"],
                    "case_version": memory.version,
                    "verification_findings": result["verification"],
                    "model_ids": [
                        config.openai_chat_model,
                        config.openai_review_model,
                        config.openai_web_search_model,
                    ],
                    "prompt_versions": ["v1-research"],
                    "corpus_version": "live-web-passages-only",
                    "token_usage": state["token_usage"],
                    "model_calls": state["model_calls"],
                    "evaluation_status": "passed_observable_slice"
                    if result["verification"]["passed"] and passages
                    else "failed_or_limited",
                    "reviewer_notes": "Live fetch/generation/review slice using actual search URLs. Earlier complete graph run was limited; this is not a second full end-to-end run. Lawyer review pending.",
                }
            )
        finally:
            graph.connection.close()
    record["latency"] = round(time.perf_counter() - started, 3)
    with (root / "evals/raw_outputs/live-web-research-2026-11-06.jsonl").open("a") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "status": record["evaluation_status"],
                "latency": record["latency"],
                "fetched": len(record.get("retrieved_passages", [])),
                "token_usage": record.get("token_usage"),
            }
        )
    )


if __name__ == "__main__":
    main()
