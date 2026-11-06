"""Explicitly offline HTTP regression runner. No credentials or live providers used."""

import json
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def main():
    root = Path(__file__).parents[2]
    scenarios = json.loads((root / "evals/cases/request_routing.json").read_text())
    rows = []
    with tempfile.TemporaryDirectory(prefix="nyay-offline-routing-") as folder:
        # Set BEFORE importing the application: even its startup is explicitly offline.
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["REQUESTS_PER_MINUTE"] = "600"
        for env, filename in {
            "DATABASE_PATH": "app.sqlite3",
            "CHECKPOINT_PATH": "cp.sqlite3",
            "CHROMA_PATH": "chroma",
            "UPLOAD_PATH": "uploads",
            "EXPORT_PATH": "exports",
        }.items():
            os.environ[env] = str(Path(folder) / filename)
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            client.get("/api/bootstrap")
            client.headers["X-CSRF-Token"] = client.cookies["nyay_csrf"]
            for scenario in scenarios:
                cid = client.post("/api/conversations", json={"language": "en"}).json()["id"]

                def turn(message, case_id=cid):
                    return client.post(
                        f"/api/conversations/{case_id}/turns",
                        json={"content": message, "request_id": str(uuid.uuid4())},
                    )

                if scenario.get("seed"):
                    turn(scenario["seed"]).raise_for_status()
                before = client.get(f"/api/conversations/{cid}").json()["case_memory"]
                started = time.perf_counter()
                response = turn(scenario["message"])
                elapsed = time.perf_counter() - started
                response.raise_for_status()
                body = response.json()
                after = client.get(f"/api/conversations/{cid}").json()["case_memory"]
                meta = body["assistant_message"]["metadata"]
                workflows = list(dict.fromkeys(t["workflow"] for t in meta["task_plan"]))
                changed = before != after
                passed = (
                    set(workflows) == set(scenario["workflows"])
                    and changed == scenario["case_change"]
                )
                rows.append(
                    {
                        "test_id": scenario["test_id"],
                        "evaluation_mode": "offline HTTP / conservative interpreter; not live AI",
                        "input_messages": [scenario["seed"], scenario["message"]]
                        if scenario.get("seed")
                        else [scenario["message"]],
                        "attachment_ids": [],
                        "expected_behaviour": {
                            "workflows": scenario["workflows"],
                            "case_change": scenario["case_change"],
                        },
                        "actual_outputs": {
                            "answer": body["assistant_message"]["content"],
                            "workflows": workflows,
                            "case_changed": changed,
                            "interpretation": meta["interpretation"],
                        },
                        "retrieved_passages": body["sources"],
                        "tool_events": meta["tool_records"],
                        "memory_updates": after if changed else {},
                        "case_version": after["version"],
                        "verification_findings": body["verification"],
                        "model_ids": [],
                        "prompt_versions": ["request-v1"],
                        "corpus_version": app.state.retriever.corpus_version,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "latency": elapsed,
                        "token_usage": body["token_usage"],
                        "evaluation_status": "passed_offline_contract"
                        if passed
                        else "failed_offline_contract",
                        "reviewer_notes": "Synthetic offline contract only; no real-world/model/legal accuracy claim.",
                    }
                )
        app.state.assistant_graph.connection.close()
    target = root / "evals/raw_outputs/request-routing-offline-2026-11-06.jsonl"
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    metrics = {
        "mode": "offline synthetic HTTP contracts, not real model accuracy",
        "cases": len(rows),
        "passed": sum(r["evaluation_status"] == "passed_offline_contract" for r in rows),
        "routing_matches": sum(
            set(r["actual_outputs"]["workflows"]) == set(r["expected_behaviour"]["workflows"])
            for r in rows
        ),
        "unintended_case_mutations": sum(
            r["actual_outputs"]["case_changed"] and not r["expected_behaviour"]["case_change"]
            for r in rows
        ),
        "median_latency_ms": round(sorted(r["latency"] for r in rows)[len(rows) // 2] * 1000),
        "live_model_calls": 0,
        "token_consumption": 0,
        "unsupported_authority_recommendations": "no live recommendations generated; adversarial validation covered in pytest",
        "citation_errors": "not assessed by this offline response runner; covered separately in pytest",
        "tool_honesty": "configuration-required states observed; execution claims tested with labelled doubles",
    }
    (root / "evals/reports/request-routing-metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))
    if metrics["passed"] != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
