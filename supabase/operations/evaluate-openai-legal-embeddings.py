#!/usr/bin/env python3
"""Evaluate OpenAI query vectors against the versioned legal corpus and E5 case bank."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGAL_ROOT = Path(os.environ.get("NYAY_LEGAL_CHECKOUT", "/Users/ashutoshanand/.gemini/antigravity/worktrees/Nyay Sathi V2/legal_knowledge_retrieval_component"))
sys.path.insert(0, str(LEGAL_ROOT))

reembed_spec = importlib.util.spec_from_file_location("reembed", Path(__file__).with_name("reembed-legal-corpus-openai.py"))
reembed = importlib.util.module_from_spec(reembed_spec)
assert reembed_spec and reembed_spec.loader
sys.modules[reembed_spec.name] = reembed
reembed_spec.loader.exec_module(reembed)

eval_spec = importlib.util.spec_from_file_location("legal_eval", LEGAL_ROOT / "evals/legal_retrieval_eval.py")
legal_eval = importlib.util.module_from_spec(eval_spec)
assert eval_spec and eval_spec.loader
sys.modules[eval_spec.name] = legal_eval
eval_spec.loader.exec_module(legal_eval)


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right)) / max(1e-12, math.sqrt(sum(a*a for a in left)) * math.sqrt(sum(b*b for b in right)))


def main() -> int:
    reembed.load_dotenv(ROOT / ".env")
    key = os.environ.get("OPENAI_EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OpenAI embedding key is required")
    passages = json.loads((ROOT / "data/legal_corpus/v1/passages.json").read_text())
    cases = legal_eval.EVAL_CASES
    queries = [case.query for case in cases]
    fingerprint = hashlib.sha256(json.dumps({"model": reembed.MODEL, "dimensions": reembed.DIMENSIONS, "queries": queries}, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    cache_path = ROOT / "runtime/openai-legal-query-embedding-checkpoint.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if cache.get("fingerprint") == fingerprint:
        query_vectors, tokens = cache["vectors"], int(cache["input_tokens"])
    else:
        query_vectors, tokens = reembed.embed(queries, key, [0])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        reembed.atomic_write(cache_path, json.dumps({"fingerprint": fingerprint, "vectors": query_vectors, "input_tokens": tokens}))
    rows = []
    supported_top_scores = []
    unsupported_top_scores = []
    for case, vector in zip(cases, query_vectors):
        target = case.incident_date or "2026-11-20"
        eligible = legal_eval._eligible(passages, case.region, target, case.incident_date is not None)
        ranked = sorted(((p["passageId"], cosine(vector, p["embedding"])) for p in eligible), key=lambda row: row[1], reverse=True)
        top_ids = [pid for pid, _ in ranked[:5]]
        forbidden = [pid for pid in top_ids if pid in case.forbidden_ids]
        expected_rank = next((i + 1 for i, (pid, _) in enumerate(ranked[:5]) if pid in case.expected_any_ids), None)
        top_score = ranked[0][1] if ranked else 0.0
        (unsupported_top_scores if case.expect_empty else supported_top_scores).append(top_score)
        rows.append({"case_id": case.case_id, "category": case.category, "top_score": round(top_score, 6), "expected_rank_at_5": expected_rank, "forbidden_ids_at_5": forbidden, "top_ids": top_ids})
    report = {
        "embedding_config": {"embedding_model": reembed.MODEL, "embedding_version": reembed.VERSION, "embedding_dimensions": reembed.DIMENSIONS, "similarity_metric": "cosine"},
        "corpus_version": json.loads((ROOT / "data/legal_corpus/v1/corpus_manifest.json").read_text())["corpus_version"],
        "query_input_tokens": tokens,
        "summary": {
            "cases": len(rows),
            "expected_recall_at_5": round(sum(r["expected_rank_at_5"] is not None and not r["forbidden_ids_at_5"] for r in rows if not r["case_id"].startswith("unsupported_")) / 12, 4),
            "forbidden_violations": sum(bool(r["forbidden_ids_at_5"]) for r in rows),
            "supported_top_score_min": round(min(supported_top_scores), 6),
            "unsupported_top_score_max": round(max(unsupported_top_scores), 6),
        },
        "details": rows,
    }
    output = ROOT / "data/legal_corpus/v1/openai_embedding_qualification.json"
    reembed.atomic_write(output, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    fixtures = {case.case_id: {"query": case.query, "embedding": vector} for case, vector in zip(cases, query_vectors)}
    reembed.atomic_write(ROOT / "frontend/src/fixtures/openai-legal-query-embeddings.json", json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")) + "\n")
    case_fixture = [{
        "case_id": case.case_id, "query": case.query, "region": case.region,
        "incident_date": case.incident_date, "expected_any_ids": list(case.expected_any_ids),
        "forbidden_ids": list(case.forbidden_ids), "expect_empty": case.expect_empty,
    } for case in cases]
    reembed.atomic_write(ROOT / "frontend/src/fixtures/legal-retrieval-qualification-cases.json", json.dumps(case_fixture, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
