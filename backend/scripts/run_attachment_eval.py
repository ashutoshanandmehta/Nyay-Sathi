"""Budgeted live, synthetic attachment regression. Never reads personal evidence."""

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.main import app


def main():
    settings = app.state.settings
    if (
        not settings.ai_configured
        or settings.live_eval_max_cases < 1
        or settings.live_eval_max_model_calls < 5
    ):
        print("Not run: missing credentials or insufficient live evaluation budget.")
        return
    output = Path(__file__).parents[2] / "evals/raw_outputs/live-attachments-2026-11-06.jsonl"
    scenarios = [
        (
            "invoice-colour",
            "I ordered a bedsheet but it is not the same colour. How do I raise a complaint? I attached the invoice.",
            True,
        ),
        ("refund-intake", "My refund has not arrived", False),
    ]
    for test_id, message, attach in scenarios[
        : min(settings.live_eval_max_cases, settings.live_eval_max_model_calls // 5)
    ]:
        with TestClient(app) as client:
            client.get("/api/bootstrap")
            client.headers["X-CSRF-Token"] = client.cookies["nyay_csrf"]
            cid = client.post("/api/conversations", json={"language": "en"}).json()["id"]
            ids = []
            try:
                if attach:
                    pdf = fitz.open()
                    for index in range(8):
                        page = pdf.new_page()
                        page.insert_text(
                            (60, 60),
                            "Synthetic invoice: HomeStore, bedsheet, blue, INR 2300. Order TEST-123."
                            if index == 7
                            else "Synthetic terms of purchase for extraction testing. No case facts on this page.",
                        )
                    response = client.post(
                        f"/api/conversations/{cid}/attachments",
                        files={"file": ("synthetic-invoice.pdf", pdf.tobytes(), "application/pdf")},
                    )
                    pdf.close()
                    response.raise_for_status()
                    ids = [response.json()["id"]]
                started = time.perf_counter()
                response = client.post(
                    f"/api/conversations/{cid}/turns",
                    json={
                        "content": message,
                        "request_id": str(uuid.uuid4()),
                        "attachment_ids": ids,
                        "language": "en",
                    },
                )
                latency = round(time.perf_counter() - started, 3)
                payload = response.json()
                detail = client.get(f"/api/conversations/{cid}").json()
                metadata = payload.get("assistant_message", {}).get("metadata", {})
                record = {
                    "test_id": test_id,
                    "input_messages": [message],
                    "attachment_ids": ids,
                    "expected_behaviour": [
                        "Useful consumer assistance",
                        "No invented facts or dates",
                        "Use document as attributed evidence",
                        "Review before display",
                    ],
                    "actual_outputs": payload,
                    "retrieved_passages": metadata.get("sources", []),
                    "tool_events": metadata.get("events", []),
                    "memory_updates": detail["case_memory"],
                    "case_version": payload.get("case_version"),
                    "verification_findings": payload.get("verification", {}),
                    "model_ids": [settings.openai_chat_model, settings.openai_review_model],
                    "prompt_versions": ["v1-evidence-rereview"],
                    "corpus_version": app.state.retriever.corpus_version,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "latency": latency,
                    "token_usage": payload.get("token_usage", {}),
                    "evaluation_status": "passed_automated_review"
                    if payload.get("verification", {}).get("passed")
                    else "failed_or_withheld",
                    "reviewer_notes": "Synthetic live run. Model review does not establish legal correctness. Indian lawyer review pending.",
                }
                with output.open("a") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(
                    json.dumps(
                        {
                            "test_id": test_id,
                            "http_status": response.status_code,
                            "latency": latency,
                            "evaluation_status": record["evaluation_status"],
                        }
                    )
                )
            finally:
                client.delete(f"/api/conversations/{cid}")


if __name__ == "__main__":
    main()
