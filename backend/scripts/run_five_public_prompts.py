"""Explicitly authorized sequential live run; no mocked providers or auto reruns.

Existing public vectors may be queried, but this runner never builds/re-embeds an
index. Private application stores are temporary. Outputs are actual HTTP replies.
"""

import argparse
import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings, get_settings

CASES = [
    (
        "amazon-delivery",
        "I bought an induction cooktop from Amazon for ₹1,399. It was marked delivered, but I never received it. Support arranged a replacement, which was delayed and then marked undeliverable. They promised a refund but later refused it, citing previous missing-item claims. What evidence should I collect? Prepare a factual complaint summary and suggest the next practical step.",
        ["Cover evidence, summary and next step", "Recognize earlier complaint and refund refusal"],
    ),
    (
        "blinkit-milk",
        "Milk delivered through Blinkit curdled when heated. This has happened three times. Support says replacements are unavailable and offers refunds, but ordering again costs another ₹72 in delivery and handling charges. Is the milk suitable to consume? Draft a short message asking them to address the repeated problem and additional charges.",
        ["Handle safety and complaint drafting separately", "No unsupported food-safety diagnosis"],
    ),
    (
        "goibibo-checkin",
        "We are both 18 and booked a hotel through Goibibo. The listing said guests aged 18 were allowed, but the hotel refused check-in, saying we needed to be 19. They told us to cancel and promised a refund, then rejected the cancellation. Later they claimed the minimum age was 21. Who should I approach, and what should my complaint say?",
        [
            "Recognize unfamiliar platform and property roles",
            "Preserve conflicting policy statements",
        ],
    ),
    (
        "chennai-wages",
        "My mother worked at a restaurant in Chennai for several years. Her March salary and part of April’s wages remain unpaid. We repeatedly approached the police, but the employer kept promising payment without paying. We then contacted the CM Cell and were told the matter was forwarded to the Labour Department. What records should we prepare? Write a factual brief for a lawyer without making us restart the complaint.",
        [
            "Route employment rather than consumer",
            "Prepare records and factual handoff using prior escalation",
        ],
    ),
    (
        "refund-fraud",
        "A damaged curd packet arrived in my Blinkit order. I searched online for customer care and called a number I found. Someone sent me a WhatsApp link to upload a photo, then asked me to check Google Pay. Afterwards, ₹98,000 was debited from my bank account. What should I prioritise now, and what evidence should I preserve?",
        ["Prioritize suspected financial fraud", "Do not request PIN, OTP or credentials"],
    ),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authorized-five-case-budget", action="store_true")
    args = parser.parse_args()
    if not args.live or not args.authorized_five_case_budget:
        raise SystemExit("Not run: explicit live/five-case budget flags required.")
    configured = Settings()
    from scripts.live_guard import require_live_budget
    require_live_budget(configured, minimum_requests=25, cases=5)
    if not configured.ai_configured:
        raise SystemExit("Not run: backend key is not configured.")
    root = Path(__file__).parents[2]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = root / f"evals/raw_outputs/live-five-public-prompts-{stamp}.jsonl"
    report = root / f"evals/reports/five-public-prompts-{stamp}.md"
    prompt_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "backend/app/prompts/v1").glob("*.md")
    }
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.ERROR)
    rows = []
    with tempfile.TemporaryDirectory(prefix="nyay-five-live-") as folder:
        directory = Path(folder)
        # Avoid a startup embedding rebuild. The real key remains only in backend Settings.
        os.environ["OPENAI_API_KEY"] = ""
        for variable, filename in {
            "DATABASE_PATH": "app.sqlite3",
            "CHECKPOINT_PATH": "cp.sqlite3",
            "CHROMA_PATH": "unused-chroma",
            "UPLOAD_PATH": "uploads",
            "EXPORT_PATH": "exports",
        }.items():
            os.environ[variable] = str(directory / filename)
        get_settings.cache_clear()
        from fastapi.testclient import TestClient

        from app.db import Database
        from app.graph.workflow import AssistantGraph
        from app.main import app
        from app.rag.retrieval import HybridRetriever
        from app.security.ownership import token_hash

        live = configured.model_copy(
            update={
                "database_path": directory / "app.sqlite3",
                "checkpoint_path": directory / "cp.sqlite3",
                "upload_path": directory / "uploads",
                "export_path": directory / "exports",
                "max_model_calls_per_turn": 5,
                "live_eval_max_cases": 5,
                "live_eval_max_model_calls": 25,
                "web_max_queries": 1,
            }
        )
        live.ensure_dirs()
        retriever = HybridRetriever(live.model_copy(update={"openai_api_key": None}))
        retrieval_mode = "BM25; existing vectors unavailable; no index rebuild attempted"
        embedding_events = []
        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            embedding = OpenAIEmbeddingFunction(
                api_key=configured.openai_api_key, model_name=configured.openai_embedding_model
            )
            embedding.client = embedding.client.with_options(
                max_retries=0, timeout=live.model_timeout_seconds
            )
            original_embedding_call = embedding.client.embeddings.create

            def measured_embedding(*args, **kwargs):
                event = {"status": "attempted"}
                embedding_events.append(event)
                try:
                    result = original_embedding_call(*args, **kwargs)
                    event.update(status="completed", token_usage=result.usage.model_dump())
                    return result
                except Exception as exc:
                    event.update(status="failed", error_type=type(exc).__name__)
                    raise

            embedding.client.embeddings.create = measured_embedding
            collection = chromadb.PersistentClient(path=str(configured.chroma_path)).get_collection(
                "official_consumer_law_v1",
                embedding_function=embedding,
            )
            if collection.count():
                retriever.collection = collection
                retrieval_mode = "BM25 plus existing OpenAI/Chroma vectors; no index rebuild"
        except Exception as exc:
            retrieval_mode += f" ({type(exc).__name__})"
        app.state.assistant_graph.connection.close()
        graph = AssistantGraph(live, retriever)
        app.state.settings, app.state.db = live, Database(live.database_path)
        app.state.retriever, app.state.assistant_graph = retriever, graph
        app.state.requests.clear()
        app.dependency_overrides[get_settings] = lambda: live
        print(
            json.dumps(
                {
                    "started": True,
                    "cases": 5,
                    "generation_search_call_cap": 25,
                    "per_case_cap": 5,
                    "retrieval": retrieval_mode,
                }
            ),
            flush=True,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/api/bootstrap").raise_for_status()
            client.headers["X-CSRF-Token"] = client.cookies["nyay_csrf"]
            owner_id = app.state.db.owner_for_hash(token_hash(client.cookies["nyay_owner"]))
            for index, (identifier, message, expectations) in enumerate(CASES, 1):
                cid = client.post("/api/conversations", json={"language": "en"}).json()["id"]
                print(
                    json.dumps({"case": index, "id": identifier, "stage": "starting"}), flush=True
                )
                started = time.perf_counter()
                embedding_start = len(embedding_events)
                response = client.post(
                    f"/api/conversations/{cid}/turns",
                    json={"content": message, "request_id": str(uuid.uuid4())},
                )
                detail = client.get(f"/api/conversations/{cid}").json()
                checkpoint = graph.graph.get_state(
                    {"configurable": {"thread_id": f"{owner_id}:{cid}"}}
                ).values
                body = response.json()
                assistant = body.get("assistant_message") or next(
                    (m for m in reversed(detail.get("messages", [])) if m["role"] == "assistant"),
                    {},
                )
                meta = assistant.get("metadata", {})
                verified = meta.get("verification", {})
                row = {
                    "test_id": identifier,
                    "input_messages": [message],
                    "attachment_ids": [],
                    "expected_behaviour": expectations,
                    "actual_outputs": {
                        "http_status": response.status_code,
                        "answer": assistant.get("content"),
                        "error": body.get("detail") if response.status_code != 200 else None,
                    },
                    "retrieved_passages": meta.get("sources", checkpoint.get("passages", [])),
                    "tool_events": meta.get("events", checkpoint.get("events", [])),
                    "tool_records": meta.get("tool_records", checkpoint.get("tool_records", [])),
                    "interpretation": meta.get(
                        "interpretation", checkpoint.get("interpretation", {})
                    ),
                    "task_plan": meta.get("task_plan", checkpoint.get("task_plan", [])),
                    "memory_updates": detail.get("case_memory", {}),
                    "case_version": detail.get("case_memory", {}).get("version"),
                    "verification_findings": verified or checkpoint.get("verification", {}),
                    "review_findings": checkpoint.get("feedback_review", {}),
                    "candidate_units": checkpoint.get("candidate_batch", {}),
                    "claim_review": checkpoint.get("unit_review", {}),
                    "unit_outcomes": checkpoint.get("unit_outcomes", []),
                    "publication_status": checkpoint.get("publication_status"),
                    "model_ids": {
                        "chat": live.openai_chat_model,
                        "review": live.openai_review_model,
                        "search": live.openai_web_search_model,
                        "embedding": live.openai_embedding_model,
                    },
                    "prompt_versions": prompt_hashes,
                    "corpus_version": retriever.corpus_version,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "latency": round(time.perf_counter() - started, 3),
                    "token_usage": meta.get("token_usage", checkpoint.get("token_usage", {})),
                    "model_calls": checkpoint.get("model_calls", 0),
                    "configured_per_case_cap": 5,
                    "embedding_events": embedding_events[embedding_start:],
                    "retrieval_mode": retrieval_mode,
                    "evaluation_status": "passed_automated_review"
                    if response.status_code == 200 and verified.get("passed")
                    else "failed_or_limited",
                    "reviewer_notes": "Actual sequential live HTTP application run. No provider mocks. No automatic reruns. Automated review is not legal correctness; lawyer review pending.",
                }
                with output.open("a") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "case": index,
                            "id": identifier,
                            "status": row["evaluation_status"],
                            "http_status": response.status_code,
                            "latency": row["latency"],
                            "model_calls": row["model_calls"],
                            "token_usage": row["token_usage"],
                        }
                    ),
                    flush=True,
                )
        graph.connection.close()
        app.dependency_overrides.clear()
    contents = [
        "# Five public-account prompts: actual live responses",
        "",
        "Sequential run. Five-call cap per prompt; no automatic reruns. Temporary private chats were removed. Model review is not legal validation.",
        "",
    ]
    for number, row in enumerate(rows, 1):
        contents += [
            f"## {number}. {row['test_id']}",
            "",
            f"Status: {row['evaluation_status']}; HTTP {row['actual_outputs']['http_status']}; {row['latency']} seconds; {row['model_calls']} reported model calls.",
            "",
            "Prompt:",
            "",
            row["input_messages"][0],
            "",
            "Actual response:",
            "",
            row["actual_outputs"]["answer"] or "No assistant response was returned.",
            "",
        ]
    report.write_text("\n".join(contents))
    print(
        json.dumps(
            {
                "complete": True,
                "raw_output": str(output),
                "report": str(report),
                "reported_model_calls": sum(r["model_calls"] for r in rows),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
