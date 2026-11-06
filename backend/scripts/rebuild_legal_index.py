"""Synchronise the persistent Chroma collection with the versioned legal corpus."""

import argparse
import json

from app.config import Settings
from app.rag.retrieval import HybridRetriever


def main() -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--embed-missing",
        action="store_true",
        help="Explicitly authorize paid embedding of missing corpus passages",
    )
    args = parser.parse_args()
    if not args.embed_missing:
        raise SystemExit("Not run: --embed-missing explicitly opts into paid index maintenance.")
    settings.vector_index_enabled = True
    if not settings.ai_configured:
        print(json.dumps({"status": "not_run", "reason": "OPENAI_API_KEY is not configured"}))
        return 2
    retriever = HybridRetriever(settings)
    if retriever.collection is None:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "Chroma/OpenAI embedding initialisation failed; no vector success is claimed",
                    "lexical_passages": len(retriever.passages),
                }
            )
        )
        return 1
    vector_count = retriever.collection.count()
    existing = set(retriever.collection.get(include=[])["ids"])
    missing = [p for p in retriever.passages if p["passage_id"] not in existing]
    if missing:
        retriever.collection.add(
            ids=[p["passage_id"] for p in missing],
            documents=[p["text"] for p in missing],
            metadatas=[{"source_id": p["source_id"], "locator": p["locator"]} for p in missing],
        )
        vector_count = retriever.collection.count()
    smoke = retriever.search("consumer non-delivery refund evidence procedure", limit=3)
    report = {
        "status": "ok",
        "corpus_version": retriever.corpus_version,
        "lexical_passages": len(retriever.passages),
        "vector_passages": vector_count,
        "smoke_passage_ids": [item["passage_id"] for item in smoke],
    }
    print(json.dumps(report))
    return 0 if vector_count == len(retriever.passages) else 1


if __name__ == "__main__":
    raise SystemExit(main())
