"""Authorized sequential live HTTP evaluation, with a shared hard API budget.

No mocked model/search outputs, no automatic reruns, no source-index rebuild.
The generation/search budget excludes the separately capped query embeddings,
matching the application's existing model-call counters.
"""

import argparse
import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
import warnings
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings, get_settings

CASES = [
    {
        "id": "amazon-two-fans",
        "source_url": "https://www.reddit.com/r/LegalAdviceIndia/comments/1t0o6yq/need_advice_regarding_amazon_refund_issue_and/",
        "message": "I ordered three fans from Amazon. Two were the wrong colour, so I requested returns for both. Support registered only one return, but my father handed both fans to the pickup agent, who accepted them. I received only one refund.\n\nSupport repeatedly promised to arrange the remaining refund, but later closed the investigation because their records showed only one returned item. I also emailed the grievance team, who redirected me to regular support. I have emails, call history and refund assurances.\n\nWhat evidence should I collect? Prepare a factual complaint summary and suggest the next practical step, considering cost and effort.",
        "expected": [
            "Recognize support/grievance escalation already attempted",
            "Cover evidence, summary and practical next step",
            "Do not treat alleged pickup as independent proof",
        ],
    },
    {
        "id": "blinkit-expired-milk",
        "source_url": "https://www.reddit.com/r/FuckBlinkit/comments/1ufm708/blinkit_sent_me_expired_milk/",
        "message": "I ordered groceries through Blinkit around 12:30 am and received milk that was already expired. I emailed support, but they refused both replacement and refund.\n\nIs the milk safe to consume? What evidence should I preserve? Draft a short message challenging their refusal and asking for a refund.",
        "expected": [
            "Independently handle safety, evidence and drafting",
            "Preserve supported correspondence even if safety research is unavailable",
            "Do not invent illness or a clinical finding",
        ],
    },
    {
        "id": "employment-unpaid-salary",
        "source_url": "https://www.reddit.com/r/LegalAdviceIndia/comments/1rpt9al/ex_employer_not_playing_salary_dues/",
        "message": "I worked at an event-management startup from April to September 2025. On 30 September, my company access was removed and I received a termination email identifying that date as my last working day. Around ₹60,000 in salary remained unpaid as of March 2026.\n\nI had already sent a written payment request through WhatsApp and email, describing my work and asking when I would be paid. The founder replied only with a question mark. My appointment letter describes my salary and final settlement.\n\nPrepare an evidence checklist and a factual brief for a lawyer. What additional details are needed to identify the appropriate complaint authority?",
        "expected": [
            "Route employment, not consumer/NCH",
            "Preserve historical dates and existing demand",
            "Prepare evidence checklist and lawyer brief with bounded authority clarification",
        ],
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--case",
        choices=[c["id"] for c in CASES],
        help="Run only the selected case; never reruns automatically",
    )
    args = parser.parse_args()
    cases = [c for c in CASES if not args.case or c["id"] == args.case]
    if not args.live:
        raise SystemExit("Not run: pass --live only for an authorized paid evaluation.")
    configured = Settings()
    from scripts.live_guard import require_live_budget
    require_live_budget(configured, minimum_requests=len(cases) * 3, cases=len(cases))
    if not configured.ai_configured:
        raise SystemExit("Not run: backend API key is not configured.")
    if configured.live_eval_max_cases < len(cases) or configured.live_eval_max_model_calls < 3:
        raise SystemExit("Not run: configured live case/call budget is insufficient.")
    per_case = min(
        4, configured.max_model_calls_per_turn, configured.live_eval_max_model_calls // len(cases)
    )
    generation_cap, embedding_cap = per_case * len(cases), len(cases)
    root = Path(__file__).parents[2]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw = root / f"evals/raw_outputs/live-public-prompts-{len(cases)}-{stamp}.jsonl"
    report = root / f"evals/reports/public-prompts-{len(cases)}-{stamp}.md"
    prompt_hashes = {
        str(path.relative_to(root / "backend")): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root / "backend/app/prompts").rglob("*.md")
    }
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="chromadb.*")

    # Guard actual provider requests, independently of graph-reported usage.
    # OpenAI 3.45 uses httpx2 internally; FastAPI TestClient still uses httpx.
    # Intercept the installed SDK transport rather than the unrelated test client.
    import httpx2 as httpx

    original_send = httpx.Client.send
    requests = []
    active_case = {"id": None}

    def budgeted_send(client, request, *a, **kw):
        path = request.url.path
        operation = (
            "embedding"
            if path.endswith("/embeddings")
            else "generation_search"
            if path.endswith(("/responses", "/chat/completions"))
            else None
        )
        if not operation:
            return original_send(client, request, *a, **kw)
        cap = embedding_cap if operation == "embedding" else generation_cap
        if sum(r["operation"] == operation for r in requests) >= cap:
            raise RuntimeError("Evaluation request budget exhausted before transmission")
        if (
            operation == "generation_search"
            and sum(
                r["operation"] == operation and r["case_id"] == active_case["id"] for r in requests
            )
            >= per_case
        ):
            raise RuntimeError("Case request budget exhausted before transmission")
        event = {"operation": operation, "case_id": active_case["id"], "status": "attempted"}
        requests.append(event)
        started = time.perf_counter()
        try:
            response = original_send(client, request, *a, **kw)
            data = json.loads(response.read())
            event.update(
                status="completed" if response.is_success else "http_error",
                http_status=response.status_code,
                model=data.get("model"),
                token_usage=data.get("usage", {}),
            )
            if not response.is_success:
                error = data.get("error", {})
                event["error"] = {
                    k: str(error[k])[:100] for k in ("type", "code", "param") if error.get(k)
                }
            return response
        except Exception as exc:
            event.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            event["latency_seconds"] = round(time.perf_counter() - started, 3)
            print(json.dumps({"provider_request": event}), flush=True)

    httpx.Client.send = budgeted_send
    rows = []
    try:
        with tempfile.TemporaryDirectory(prefix="nyay-three-live-") as folder:
            directory = Path(folder)
            # Import startup without a key so it cannot rebuild paid embeddings.
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
            from app.services.progress import publisher

            live = configured.model_copy(
                update={
                    "database_path": directory / "app.sqlite3",
                    "checkpoint_path": directory / "cp.sqlite3",
                    "upload_path": directory / "uploads",
                    "export_path": directory / "exports",
                    "max_model_calls_per_turn": per_case,
                    "model_timeout_seconds": max(65.0, configured.model_timeout_seconds),
                    "web_max_queries": 1,
                }
            )
            live.ensure_dirs()
            retriever = HybridRetriever(live.model_copy(update={"openai_api_key": None}))
            retrieval_mode = "BM25 only; existing vectors unavailable; no rebuild"
            try:
                import chromadb
                from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

                embedding = OpenAIEmbeddingFunction(
                    api_key=configured.openai_api_key, model_name=configured.openai_embedding_model
                )
                embedding.client = embedding.client.with_options(
                    max_retries=0, timeout=live.model_timeout_seconds
                )
                collection = chromadb.PersistentClient(
                    path=str(configured.chroma_path)
                ).get_collection("official_consumer_law_v1", embedding_function=embedding)
                if collection.count():
                    retriever.collection = collection
                    retrieval_mode = "BM25 plus existing OpenAI/Chroma vectors; no rebuild"
            except Exception as exc:
                retrieval_mode += f" ({type(exc).__name__})"
            retriever.settings = live  # Managed query embedding only; never rebuild the corpus.
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
                        "cases": len(cases),
                        "per_case_generation_search_cap": per_case,
                        "generation_search_cap": generation_cap,
                        "query_embedding_cap": embedding_cap,
                        "retrieval": retrieval_mode,
                    }
                ),
                flush=True,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                client.get("/api/bootstrap").raise_for_status()
                client.headers["X-CSRF-Token"] = client.cookies["nyay_csrf"]
                owner = app.state.db.owner_for_hash(token_hash(client.cookies["nyay_owner"]))
                for case in cases:
                    active_case["id"] = case["id"]
                    print(json.dumps({"case": case["id"], "stage": "starting"}), flush=True)
                    cid = client.post("/api/conversations", json={"language": "en"}).json()["id"]
                    started, request_start = time.perf_counter(), len(requests)
                    progress = []

                    def on_progress(event, progress=progress, case_id=case["id"]):
                        progress.append(event)
                        print(json.dumps({"case": case_id, "progress": event}), flush=True)

                    token = publisher.set(on_progress)
                    try:
                        response = client.post(
                            f"/api/conversations/{cid}/turns",
                            json={"content": case["message"], "request_id": str(uuid.uuid4())},
                        )
                    finally:
                        publisher.reset(token)
                    detail = client.get(f"/api/conversations/{cid}").json()
                    state = graph.graph.get_state(
                        {"configurable": {"thread_id": f"{owner}:{cid}"}}
                    ).values
                    body = response.json()
                    assistant = body.get("assistant_message") or next(
                        (
                            m
                            for m in reversed(detail.get("messages", []))
                            if m["role"] == "assistant"
                        ),
                        {},
                    )
                    meta = assistant.get("metadata", {})
                    row = {
                        "test_id": case["id"],
                        "source_url": case["source_url"],
                        "input_messages": [case["message"]],
                        "attachment_ids": [],
                        "expected_behaviour": case["expected"],
                        "actual_outputs": {
                            "http_status": response.status_code,
                            "answer": assistant.get("content"),
                            "error": body.get("detail") if response.status_code != 200 else None,
                        },
                        "retrieved_passages": state.get("passages", []),
                        "published_sources": meta.get("sources", []),
                        "tool_events": meta.get("events", state.get("events", [])),
                        "tool_records": state.get("tool_records", []),
                        "interpretation": state.get("interpretation", {}),
                        "interpretation_status": state.get("interpretation_status"),
                        "task_plan": state.get("task_plan", []),
                        "candidate_units": state.get("candidate_batch", {}),
                        "claim_review": state.get("unit_review", {}),
                        "unit_outcomes": state.get("unit_outcomes", []),
                        "memory_updates": detail.get("case_memory", {}),
                        "staged_case_proposals": detail.get("case_proposals", []),
                        "drafts": detail.get("drafts", []),
                        "case_version": detail.get("case_memory", {}).get("version"),
                        "staged_patches": detail.get("staged_patches", []),
                        "call_telemetry": state.get("call_telemetry", []),
                        "usage_completeness": state.get("usage_completeness", "unknown"),
                        "commit_receipt": meta.get("commit_receipt"),
                        "verification_findings": meta.get(
                            "verification", state.get("verification", {})
                        ),
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
                        "token_usage": meta.get("token_usage", state.get("token_usage", {})),
                        "model_calls": state.get("model_calls", 0),
                        "provider_requests": requests[request_start:],
                        "evaluation_status": state.get("publication_status", "execution_failed"),
                        "retrieval_mode": retrieval_mode,
                        "reviewer_notes": "Actual live HTTP responses; no provider mocks or reruns. Four-call test cap can defer web research. Automated findings are not proof of legal correctness; human/lawyer review pending.",
                    }
                    raw.parent.mkdir(parents=True, exist_ok=True)
                    with raw.open("a") as stream:
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows.append(row)
                    print(
                        json.dumps(
                            {
                                "case": case["id"],
                                "stage": "complete",
                                "http_status": response.status_code,
                                "publication_status": row["evaluation_status"],
                                "latency": row["latency"],
                                "model_calls": row["model_calls"],
                            }
                        ),
                        flush=True,
                    )
            graph.connection.close()
            app.dependency_overrides.clear()
    finally:
        httpx.Client.send = original_send

    content = [
        f"# {len(cases)} public-account prompt(s) — actual live responses",
        "",
        f"Sequential run; {per_case} generation/search calls per case, {generation_cap} shared cap; query embeddings counted separately. No model substitution, automatic rerun or corpus re-embedding. Temporary chats removed. Human/legal review pending.",
        "",
    ]
    for row in rows:
        content += [
            f"## {row['test_id']}",
            "",
            f"Source: {row['source_url']}",
            "",
            f"HTTP {row['actual_outputs']['http_status']}; publication status {row['evaluation_status']}; {row['latency']} seconds; {row['model_calls']} reported model calls.",
            "",
            "Prompt:",
            row["input_messages"][0],
            "",
            "Actual response:",
            row["actual_outputs"]["answer"] or "No assistant answer returned.",
            "",
        ]
    report.write_text("\n".join(content))
    summary = {
        "cases": len(rows),
        "statuses": {r["test_id"]: r["evaluation_status"] for r in rows},
        "provider_requests": requests,
        "reported_graph_model_calls": sum(r["model_calls"] for r in rows),
        "instrumentation_status": "observed" if requests else "unavailable",
        "generation_search_requests": sum(r["operation"] == "generation_search" for r in requests)
        if requests
        else None,
        "query_embedding_requests": sum(r["operation"] == "embedding" for r in requests)
        if requests
        else None,
        "generation_search_cap": generation_cap,
        "query_embedding_cap": embedding_cap,
        "raw_output": str(raw),
        "report": str(report),
    }
    report.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {"complete": True, **{k: v for k, v in summary.items() if k != "provider_requests"}}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
