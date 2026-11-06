import hashlib
import json
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from app.config import Settings


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\u0900-\u097f]+", text.casefold())


class HybridRetriever:
    """BM25 + OpenAI/Chroma retrieval combined with reciprocal rank fusion."""

    def __init__(self, settings: Settings):
        self.settings = settings
        passages_path = Path(__file__).parents[3] / "data" / "sources" / "consumer_passages.json"
        curated = json.loads(passages_path.read_text()) if passages_path.exists() else []
        self.curated_ids = {item["passage_id"] for item in curated}
        self.passages: list[dict[str, Any]] = curated
        ingested_path = passages_path.with_name("ingested_passages.json")
        if ingested_path.exists():
            self.passages.extend(json.loads(ingested_path.read_text()))
        self.bm25 = (
            BM25Okapi([tokenize(p["text"]) for p in self.passages]) if self.passages else None
        )
        self.collection = None
        if settings.vector_index_enabled and settings.ai_configured and self.passages:
            try:
                import chromadb
                from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

                client = chromadb.PersistentClient(path=str(settings.chroma_path))
                ef = OpenAIEmbeddingFunction(
                    api_key=settings.openai_api_key, model_name=settings.openai_embedding_model
                )
                self.collection = client.get_or_create_collection(
                    "official_consumer_law_v1",
                    embedding_function=ef,
                    metadata={"hnsw:space": "cosine"},
                )
                existing = set(self.collection.get(include=[])["ids"])
                current = {p["passage_id"] for p in self.passages}
                stale = sorted(existing - current)
                if stale:
                    self.collection.delete(ids=stale)
                # Index creation/embedding is an explicit maintenance operation,
                # never a paid side effect of importing the application.
            except Exception:
                self.collection = None

    @staticmethod
    def rewrite_query(original: str, context: dict[str, Any]) -> str:
        facts = context.get("confirmed_and_reported_facts", {})
        issue = facts.get("issue_type", {}).get("value", "consumer dispute")
        remedy = facts.get("requested_remedy", {}).get("value", "")
        return (
            f"{original} | India Consumer Protection Act 2019 | issue: {issue} | remedy: {remedy}"[
                :1000
            ]
        )

    def search(self, query: str, limit: int = 5, task_context=None) -> list[dict[str, Any]]:
        from app.routing.task_context import ApplicabilityPolicy

        if task_context is not None and "official_consumer" not in task_context.allowed_corpora:
            return []
        if not self.passages:
            return []
        rankings: list[list[str]] = []
        eligible = [
            p
            for p in self.passages
            if task_context is None or ApplicabilityPolicy.permits(task_context, p)
        ]
        sparse = (
            self.bm25
            if task_context is None
            else BM25Okapi([tokenize(p["text"]) for p in eligible])
            if eligible
            else None
        )
        if sparse:
            scores = sparse.get_scores(tokenize(query))
            rankings.append(
                [
                    eligible[i]["passage_id"]
                    for i in sorted(range(len(scores)), key=lambda x: scores[x], reverse=True)[:10]
                    if scores[i] > 0
                ]
            )
        if self.collection:
            try:
                from app.services.model_calls import active_scope, model_calls

                if active_scope.get() is not None and self.settings.ai_configured:
                    with model_calls.sdk(
                        self.settings,
                        "embedding",
                        self.settings.openai_embedding_model,
                        category="embedding",
                    ) as client:
                        embedded = client.embeddings.create(
                            model=self.settings.openai_embedding_model, input=[query]
                        )
                    result = self.collection.query(
                        query_embeddings=[embedded.data[0].embedding],
                        n_results=min(10, len(self.passages)),
                    )
                else:
                    result = self.collection.query(
                        query_texts=[query], n_results=min(10, len(self.passages))
                    )
                permitted = {p["passage_id"] for p in eligible}
                rankings.append([pid for pid in result["ids"][0] if pid in permitted])
            except Exception:
                pass
        fused: dict[str, float] = {}
        for ranking in rankings:
            for rank, pid in enumerate(ranking, 1):
                fused[pid] = fused.get(pid, 0.0) + 1 / (60 + rank)
        # The small curated set contains human-selected provision-level excerpts.
        # Boost only curated passages that already appear in a component ranking;
        # this improves sparse-only fallback without making them unconditional hits.
        for pid in set(fused) & self.curated_ids:
            fused[pid] += 0.003
        by_id = {p["passage_id"]: p for p in self.passages}
        ordered = sorted(fused, key=fused.get, reverse=True)[:limit]
        return [{**by_id[x], "rrf_score": fused[x]} for x in ordered]

    @property
    def corpus_version(self) -> str:
        payload = json.dumps(self.passages, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:12]
