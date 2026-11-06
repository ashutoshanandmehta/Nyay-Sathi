import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.rag.retrieval import HybridRetriever
from app.services.intake import deterministic_extract

ROOT = Path(__file__).parents[2]
cases = json.loads((ROOT / "evals" / "cases" / "synthetic_scenarios.json").read_text())
retriever = HybridRetriever(Settings(openai_api_key=None))
out = ROOT / "evals" / "raw_outputs" / "deterministic-2026-11-05.jsonl"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w") as stream:
    for case in cases:
        started = time.perf_counter()
        extractions = [
            deterministic_extract(message).model_dump(mode="json")
            for message in case["input_messages"]
        ]
        passages = retriever.search(case["input_messages"][-1], limit=3)
        record = {
            "test_id": case["test_id"],
            "input_messages": case["input_messages"],
            "attachment_ids": [],
            "expected_behaviour": case["expected_behaviour"],
            "actual_outputs": {"deterministic_extractions": extractions},
            "retrieved_passages": [
                {
                    "source_id": p["source_id"],
                    "passage_id": p["passage_id"],
                    "locator": p["locator"],
                }
                for p in passages
            ],
            "tool_events": [{"tool": "deterministic_extract", "count": len(extractions)}],
            "memory_updates": [x["proposed_facts"] for x in extractions],
            "case_version": None,
            "verification_findings": [],
            "model_ids": ["deterministic-no-model"],
            "prompt_versions": ["v1"],
            "corpus_version": retriever.corpus_version,
            "timestamp": datetime.now(UTC).isoformat(),
            "latency": round(time.perf_counter() - started, 6),
            "token_usage": {},
            "evaluation_status": "observed_not_legal_judgment",
            "reviewer_notes": "",
        }
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
print(json.dumps({"output": str(out), "records": len(cases), "model_calls": 0}))
