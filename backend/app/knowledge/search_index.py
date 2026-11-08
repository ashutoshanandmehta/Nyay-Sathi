"""OpenSearch-compatible hybrid legal retrieval with authority hierarchy and snippet filtering."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import date
from typing import Any

import httpx
from rank_bm25 import BM25Okapi

from app.knowledge.propositions import LegalKnowledgeFactory

STOPWORDS = {
    "what",
    "which",
    "that",
    "have",
    "with",
    "from",
    "this",
    "they",
    "their",
    "there",
    "where",
    "when",
    "would",
    "could",
    "should",
    "about",
    "into",
    "after",
    "before",
    "under",
    "india",
    "indian",
    "official",
    "sources",
}

GENERIC_INDEX_PATTERNS = re.compile(
    r"(?:table of contents|alphabetical index|list of acts|chronological list of central acts|"
    r"search results for|skip to main content.{0,80}home\s+about\s+contact|"
    r"^(?:\s*(?:section|chapter|part)\s+\d+\b[^\n]{0,45}\n){4,})",
    re.I | re.M,
)


def tokenize(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[\w\u0900-\u097f]+", text.casefold())
        if len(w) > 2 and w not in STOPWORDS
    ]


def char_trigrams(text: str) -> set[str]:
    cleaned = re.sub(r"\s+", " ", text.casefold()).strip()
    if len(cleaned) < 3:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + 3] for i in range(min(len(cleaned) - 2, 360))}


def is_generic_index_or_snippet(passage: dict[str, Any], query_terms: set[str] | None = None) -> bool:
    """Reject generic statute indexes, bare search snippets, and ultra-low-overlap boilerplate."""
    text = (passage.get("text") or "").strip()
    if len(text) < 28:
        return True
    if GENERIC_INDEX_PATTERNS.search(text):
        return True
    # High density of short navigation lines without substantive prose
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 6 and sum(len(ln) < 28 for ln in lines) / len(lines) > 0.75:
        return True
    if query_terms:
        p_terms = set(tokenize(text + " " + (passage.get("title") or "")))
        if len(query_terms) >= 3 and len(query_terms & p_terms) == 0:
            return True
    return False


class OpenSearchLegalIndex:
    """Hybrid legal index supporting remote OpenSearch clusters and local authority-first recall.

    Never sends private user text into diagnostics. Certified propositions rank ahead of
    unreviewed corpus candidates; generic statute indexes and snippets are excluded.
    """

    def __init__(
        self,
        settings,
        retriever=None,
        factory: LegalKnowledgeFactory | None = None,
        http_client=None,
    ):
        self.settings = settings
        self.factory = factory or LegalKnowledgeFactory()
        self.http_client = http_client
        self.opensearch_url: str | None = getattr(settings, "opensearch_url", None)
        self.opensearch_index: str = getattr(
            settings, "opensearch_index", "nyay_legal_propositions_v1"
        )
        self.documents: list[dict[str, Any]] = []
        self._build_local_corpus(retriever)
        self._bm25 = (
            BM25Okapi([d["_tokens"] for d in self.documents]) if self.documents else None
        )
        self.recent_diagnostics: list[dict[str, Any]] = []

    def _build_local_corpus(self, retriever) -> None:
        seen: set[str] = set()
        for prop in self.factory.certified():
            entry = prop.to_evidence_passage()
            scenario_blob = " ".join(prop.scenario_tags + prop.factual_conditions)
            tokens = tokenize(
                " ".join(
                    [
                        prop.proposition_text,
                        prop.exact_passage,
                        " ".join(prop.keywords),
                        scenario_blob,
                        prop.domain,
                        prop.authority,
                    ]
                )
            )
            entry["_tokens"] = tokens or ["law"]
            entry["_scenario_tokens"] = set(tokenize(scenario_blob + " " + " ".join(prop.keywords)))
            entry["_trigrams"] = char_trigrams(
                prop.proposition_text + " " + scenario_blob + " " + " ".join(prop.keywords)
            )
            self.documents.append(entry)
            seen.add(entry["passage_id"])

        for raw in getattr(retriever, "passages", []) or []:
            pid = raw.get("passage_id")
            if not pid or pid in seen or is_generic_index_or_snippet(raw):
                continue
            text = raw.get("text", "")
            content_hash = raw.get("content_hash") or (
                "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
            )
            source_type = raw.get("source_type") or "indian_official"
            tier = (
                1
                if "supreme court" in (raw.get("title") or "").casefold()
                else 2
                if source_type in {"primary_legislation", "statute"}
                else 3
                if source_type in {"rules", "regulation"}
                else 4
            )
            limitations = raw.get("limitations") or ""
            amendment_warning = (
                limitations
                if any(
                    w in limitations.casefold()
                    for w in ("amend", "corrigendum", "commencement", "recheck")
                )
                else ""
            )
            entry = {
                **raw,
                "origin": raw.get("origin") or "corpus",
                "content_hash": content_hash,
                "origin_verified": True,
                "certified_proposition": False,
                "source_hierarchy_tier": tier,
                "amendment_warning": amendment_warning,
                "judicial_treatment_status": raw.get("judicial_treatment_status")
                or "corpus_candidate_verify_currency",
                "verification_status": raw.get("verification_status")
                or "verified_official_candidate",
                "_tokens": tokenize((raw.get("title") or "") + " " + text) or ["law"],
                "_trigrams": char_trigrams((raw.get("title") or "") + " " + text[:400]),
            }
            self.documents.append(entry)
            seen.add(pid)

    @staticmethod
    def _effective_on(doc: dict[str, Any], as_of: date | None) -> bool:
        if as_of is None or not doc.get("effective_date"):
            return True
        try:
            return date.fromisoformat(str(doc["effective_date"])[:10]) <= as_of
        except ValueError:
            return True

    @staticmethod
    def _clean(doc: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in doc.items() if not k.startswith("_")}

    def search(
        self,
        query: str,
        *,
        jurisdiction: str | None = None,
        domain: str | None = None,
        as_of: date | None = None,
        limit: int = 5,
        certified_only: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        query_hash = hashlib.sha256(query.casefold().strip().encode("utf-8")).hexdigest()[:16]
        if self.opensearch_url:
            try:
                results = self._search_remote(
                    query,
                    jurisdiction=jurisdiction,
                    domain=domain,
                    as_of=as_of,
                    limit=limit,
                    certified_only=certified_only,
                )
                diag = self._record_diag(
                    query_hash, "opensearch_cluster", jurisdiction, domain, results, started
                )
                return results, diag
            except Exception:
                pass
        results = self._search_local(
            query,
            jurisdiction=jurisdiction,
            domain=domain,
            as_of=as_of,
            limit=limit,
            certified_only=certified_only,
        )
        diag = self._record_diag(
            query_hash, "opensearch_local_hybrid", jurisdiction, domain, results, started
        )
        return results, diag

    def _search_remote(
        self,
        query: str,
        *,
        jurisdiction: str | None,
        domain: str | None,
        as_of: date | None,
        limit: int,
        certified_only: bool,
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if jurisdiction:
            filters.append({"terms": {"jurisdiction.keyword": [jurisdiction, "India", "Central"]}})
        if domain:
            filters.append({"terms": {"domain.keyword": [domain, "constitutional_urgent"]}})
        if certified_only:
            filters.append({"term": {"certified_proposition": True}})
        if as_of:
            filters.append({"range": {"effective_date": {"lte": as_of.isoformat()}}})
        body = {
            "size": limit * 2,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query[:400],
                                "fields": ["proposition_text^3", "text^2", "title^1.5", "keywords^2"],
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
        }
        client = self.http_client or httpx
        resp = client.post(
            f"{self.opensearch_url.rstrip('/')}/{self.opensearch_index}/_search",
            json=body,
            timeout=5.0,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        q_terms = set(tokenize(query))
        out = []
        for hit in hits:
            src = hit.get("_source", {})
            if not is_generic_index_or_snippet(src, q_terms):
                out.append(src)
            if len(out) >= limit:
                break
        return out

    def _search_local(
        self,
        query: str,
        *,
        jurisdiction: str | None,
        domain: str | None,
        as_of: date | None,
        limit: int,
        certified_only: bool,
    ) -> list[dict[str, Any]]:
        if not self.documents or not self._bm25:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        q_set = set(q_tokens)
        q_trigrams = char_trigrams(query)
        bm25_scores = self._bm25.get_scores(q_tokens)
        max_bm25 = max(bm25_scores) if len(bm25_scores) and max(bm25_scores) > 0 else 1.0
        wanted_jurisdictions = (
            {jurisdiction.casefold(), "india", "central"} if jurisdiction else None
        )

        scored: list[tuple[float, dict[str, Any]]] = []
        for idx, doc in enumerate(self.documents):
            if certified_only and not doc.get("certified_proposition"):
                continue
            if wanted_jurisdictions:
                doc_j = (doc.get("jurisdiction") or "india").casefold()
                if doc_j not in wanted_jurisdictions:
                    continue
            if domain and doc.get("domain") and doc["domain"] not in {
                domain,
                "constitutional_urgent",
                "cyber_fraud",
            }:
                # Non-domain corpus items stay excluded when an explicit domain filter is set
                continue
            if not self._effective_on(doc, as_of):
                continue
            overlap = len(q_set & set(doc["_tokens"]))
            tri_union = len(q_trigrams | doc["_trigrams"]) or 1
            semantic_recall = len(q_trigrams & doc["_trigrams"]) / tri_union
            if overlap == 0 and semantic_recall < 0.18:
                continue
            lexical = float(bm25_scores[idx]) / max_bm25
            issue_overlap = overlap / max(1, min(len(q_set), 10))
            scenario_set = doc.get("_scenario_tokens") or set()
            scenario_overlap = (
                len(q_set & scenario_set) / max(1, min(len(q_set), 8)) if scenario_set else 0.0
            )
            tier = int(doc.get("source_hierarchy_tier", 4))
            hierarchy_bonus = (6 - min(5, max(1, tier))) * 0.20
            certified_bonus = 1.6 if doc.get("certified_proposition") else 0.0
            total = (
                lexical * 3.0
                + issue_overlap * 3.2
                + scenario_overlap * 2.8
                + semantic_recall * 1.4
                + hierarchy_bonus
                + certified_bonus
            )
            scored.append((total, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        per_source: dict[str, int] = {}
        for _, doc in scored:
            h = doc["content_hash"]
            sid = doc["source_id"]
            if h in seen_hashes or per_source.get(sid, 0) >= 2:
                continue
            if not doc.get("certified_proposition") and is_generic_index_or_snippet(doc, q_set):
                continue
            selected.append(self._clean(doc))
            seen_hashes.add(h)
            per_source[sid] = per_source.get(sid, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    def _record_diag(
        self,
        query_hash: str,
        backend: str,
        jurisdiction: str | None,
        domain: str | None,
        results: list[dict[str, Any]],
        started: float,
    ) -> dict[str, Any]:
        diag = {
            "query_hash": query_hash,
            "backend": backend,
            "jurisdiction_filter": jurisdiction,
            "domain_filter": domain,
            "result_count": len(results),
            "certified_hit_count": sum(1 for r in results if r.get("certified_proposition")),
            "amendment_warnings_present": any(bool(r.get("amendment_warning")) for r in results),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        self.recent_diagnostics = (self.recent_diagnostics + [diag])[-50:]
        return diag
