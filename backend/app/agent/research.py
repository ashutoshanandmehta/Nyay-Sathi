"""Concurrent, bounded research with OpenSearch hybrid certified propositions first and web gap-filling."""

import copy
import hashlib
import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from rank_bm25 import BM25Okapi

from app.agent.contracts import ResearchRequest
from app.knowledge.search_index import (
    GENERIC_PACK_KEYWORDS,
    OpenSearchLegalIndex,
    is_generic_index_or_snippet,
)
from app.routing.policy import PublicQueryPolicy
from app.routing.research import public_https_url
from app.services.model_calls import normalize_usage
from app.services.web_research import OfficialSearchProvider, ResearchRepository, SafeSourceFetcher


def canonical_url(url):
    parsed = urlparse(url)
    params = [
        (k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith(("utm_", "trk"))
    ]
    return urlunparse(
        (parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", urlencode(params), "")
    )


def authority(url):
    host = (urlparse(url).hostname or "").lower()
    if host.endswith((".gov.in", ".nic.in")) or host in {
        "rbi.org.in",
        "www.rbi.org.in",
        "sebi.gov.in",
    }:
        return "indian_official", "India", 4
    if host.endswith(".gov"):
        return "foreign_official", None, 1
    return "secondary", None, 0


STOP_TERMS = {
    "what",
    "which",
    "that",
    "have",
    "with",
    "from",
    "this",
    "they",
    "their",
    "india",
    "indian",
    "official",
    "sources",
    "legal",
    "current",
}


def tokens(text):
    return [
        w
        for w in re.findall(r"[\w\u0900-\u097f]+", text.casefold())
        if len(w) > 2 and w not in STOP_TERMS
    ]


def terms(text):
    return set(tokens(text))


DEFINITIONS_RE = re.compile(
    r"\bdefinitions?\b|unless the context otherwise requires|unless otherwise required in the context",
    re.I,
)
DEFINITION_QUERY_RE = re.compile(
    r"\b(?:what\s+(?:is|are|does)|meaning|means|definition|defined|define|kya\s+hai|matlab)\b"
    r"|मतलब|परिभाषा|क्या है",
    re.I,
)
QUERY_SECTION_RE = re.compile(r"\bsections?\s*(\d{1,3}[A-Z]{0,2})\b", re.I)
LOCATOR_SECTION_RE = re.compile(r"\bSection\s+(\d{1,3}[A-Z]{0,2})\b", re.I)


def rank_passages(passages, query, limit, per_source=2):
    """BM25 relevance plus authority; definitions rank high only for "what does X mean" queries."""
    wanted = terms(query)
    docs = [tokens(f"{p['text']} {p.get('title', '')} {p.get('locator', '')}") for p in passages]
    if not wanted or not any(docs):
        return []
    relevance = BM25Okapi(docs).get_scores(list(wanted))
    top = max(max(relevance), 1e-9)
    asks_meaning = bool(DEFINITION_QUERY_RE.search(query))
    named_sections = {n.upper() for n in QUERY_SECTION_RE.findall(query)}
    scored = []
    for p, doc, bm25 in zip(passages, docs, relevance, strict=True):
        overlap = len(wanted & set(doc))
        if not overlap:
            continue
        _, _, weight = authority(p["canonical_url"])
        score = max(bm25, 0) / top * 6 + overlap / len(wanted) * 4 + weight
        if p.get("certified_proposition"):
            score += 3.5
        if p.get("effective_date"):
            score += 0.2  # Known date is useful metadata, not proof of current law.
        locator = p.get("locator", "")
        if named_sections & {n.upper() for n in LOCATOR_SECTION_RE.findall(locator)}:
            score += 3
        if not asks_meaning and DEFINITIONS_RE.search(f"{locator} {p['text'][:200]}"):
            score *= (
                0.4  # A definitions clause shares every keyword but rarely answers the question.
            )
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected, hashes, source_counts = [], set(), {}
    for _, passage in scored:
        digest = hashlib.sha256(passage["text"].encode()).hexdigest()
        key = passage.get("source_id", passage.get("canonical_url", "default"))
        if digest in hashes or source_counts.get(key, 0) >= per_source:
            continue
        selected.append(passage)
        hashes.add(digest)
        source_counts[key] = source_counts.get(key, 0) + 1
        if len(selected) == limit:
            break
    return selected


class EvidenceCache:
    """Only public fetched text is admitted; query validation happens before access."""

    def __init__(self, path, ttl=3600, clock=time.time):
        self.path, self.ttl, self.clock = path, ttl, clock
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS public_evidence_cache (
                query_hash TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL, checked_at REAL NOT NULL, expires_at REAL NOT NULL)""")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def get(self, key):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM public_evidence_cache WHERE query_hash=? AND schema_version=1 AND expires_at>?",
                (key, self.clock()),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, passages):
        # Never cache model-generated assertions, private evidence or full request context.
        if any(
            p.get("origin") != "web" or not public_https_url(p.get("canonical_url", ""))
            for p in passages
        ):
            raise ValueError("Only public fetched passages can enter the shared cache")
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO public_evidence_cache VALUES (?,1,?,?,?)",
                (key, json.dumps(passages), self.clock(), self.clock() + self.ttl),
            )

    def invalidate(self):
        with self.connect() as conn:
            conn.execute("UPDATE public_evidence_cache SET expires_at=0")


class ResearchService:
    def __init__(
        self,
        settings,
        retriever,
        provider=None,
        fetcher=None,
        repository=None,
        cache=None,
        knowledge_index=None,
    ):
        self.settings, self.retriever = settings, retriever
        self.provider = provider or OfficialSearchProvider(settings)
        self.fetcher = fetcher or SafeSourceFetcher(settings, url_policy=public_https_url)
        self.repository = repository or ResearchRepository(settings)
        self.cache = cache or EvidenceCache(settings.database_path, settings.web_cache_ttl_seconds)
        self.knowledge_index = knowledge_index or OpenSearchLegalIndex(settings, retriever)

    def retrieve_certified(
        self,
        query_text,
        *,
        jurisdiction="India",
        domain=None,
        limit=4,
        min_relative_score=0.0,
        origin=None,
        exclude_origin=None,
    ):
        """Fast authority-first retrieval from OpenSearch/local certified propositions."""
        hits, diag = self.knowledge_index.search(
            query_text,
            jurisdiction=jurisdiction,
            domain=domain,
            limit=limit,
            min_relative_score=min_relative_score,
            origin=origin,
            exclude_origin=exclude_origin,
        )
        return hits, diag

    def run(self, request, state, budget):
        request = ResearchRequest.model_validate(request)
        with budget.lock:
            if budget.batches >= self.settings.agent_max_batches:
                return {
                    "status": "budget_exhausted",
                    "evidence": [],
                    "limitations": ["Research batch allowance reached."],
                }
            budget.batches += 1
        started = time.monotonic()
        deadline = min(budget.deadline, started + self.settings.agent_research_seconds)
        search_deadline = min(
            deadline,
            started + self.settings.agent_research_seconds * self.settings.agent_search_share,
        )
        queries, limitations, passages, records = [], [], [], []
        context = {**state.get("context", {}), "current_message": state["current_message"]}
        for question in request.questions:
            try:
                query = PublicQueryPolicy.validate(question.query, context)
                if re.search(
                    r"[\"“”]|\b(?:password|otp|aadhaar|pan number|upi pin)\b", query, re.I
                ):
                    raise ValueError("Private query syntax")
                key = hashlib.sha256(
                    (query.casefold() + "|" + (question.jurisdiction or "unknown")).encode()
                ).hexdigest()
                with budget.lock:
                    if (
                        key in budget.query_hashes
                        or budget.queries >= self.settings.agent_max_queries
                    ):
                        limitations.append("Repeated query or query allowance reached.")
                        continue
                    budget.query_hashes.add(key)
                    budget.queries += 1

                # Step 4: Retrieve certified propositions & OpenSearch hybrid candidates first.
                if not request.fresh_required:
                    kb_hits, kb_diag = self.knowledge_index.search(
                        query,
                        jurisdiction=question.jurisdiction or "India",
                        limit=4,
                    )
                    if kb_hits:
                        passages.extend(kb_hits)
                        records.append(
                            {
                                "tool": "opensearch_legal_index",
                                "status": "hit",
                                "query_hash": key,
                                "result_count": len(kb_hits),
                                "certified_hit_count": kb_diag["certified_hit_count"],
                            }
                        )

                pack_or_cert_hits = []
                if not request.fresh_required:
                    pack_hits, _ = self.retrieve_certified(
                        query,
                        jurisdiction=question.jurisdiction or "India",
                        limit=4,
                        min_relative_score=0.65,
                    )
                    pack_or_cert_hits = [
                        h
                        for h in pack_hits
                        if h.get("origin") == "official_pack" or h.get("certified_proposition")
                    ]
                if pack_or_cert_hits:
                    passages.extend(pack_or_cert_hits)
                    records.append(
                        {
                            "tool": "web_search",
                            "status": "skipped_local_coverage",
                            "query_hash": key,
                        }
                    )
                else:
                    cached = None if request.fresh_required else self.cache.get(key)
                    if cached:
                        passages.extend(cached)
                        records.append({"tool": "evidence_cache", "status": "hit", "query_hash": key})
                    else:
                        # If OpenSearch already supplied certified propositions and we are using the
                        # default live OfficialSearchProvider, skip redundant live web search unless
                        # gap-filling is needed; injected test providers still execute as requested.
                        has_strong_certified = any(p.get("certified_proposition") for p in passages)
                        if (
                            has_strong_certified
                            and not request.fresh_required
                            and isinstance(self.provider, OfficialSearchProvider)
                        ):
                            records.append(
                                {
                                    "tool": "web_search",
                                    "status": "skipped_certified_sufficient",
                                    "query_hash": key,
                                }
                            )
                        else:
                            queries.append((query, key))

                if not request.fresh_required:
                    for p in getattr(self.retriever, "passages", []):
                        try:
                            checked = datetime.fromisoformat(
                                p["retrieved_at"].replace("Z", "+00:00")
                            )
                            age = (
                                datetime.now(UTC) - checked.replace(tzinfo=checked.tzinfo or UTC)
                            ).days
                        except (KeyError, ValueError):
                            continue
                        # Two shared words that say what the problem is, not just "police".
                        shared = (terms(query) & terms(p["text"])) - GENERIC_PACK_KEYWORDS
                        if 0 <= age <= 365 and len(shared) >= 2:
                            passages.append(
                                {
                                    **p,
                                    "applicability_checked": False,
                                    "treatment_checked": False,
                                    "verification_status": "saved_candidate_requires_claim_review",
                                }
                            )
            except ValueError:
                limitations.append("A public query was rejected to protect private information.")

        if not self.settings.web_research_enabled:
            limitations.append(
                "Live search is disabled; only valid saved candidates are available."
            )
            queries = []
        if not self.settings.ai_configured and isinstance(self.provider, OfficialSearchProvider):
            limitations.append("Search needs OpenAI configuration.")
            queries = []

        def search(query, key):
            remaining = search_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            reservation = budget.reserve(
                self.settings.openai_web_search_model,
                len(query.encode()) + 2000,
                # Keep the answer continuation, its review, and the repair reserve available.
                reserve=2 + self.settings.agent_repair_reserve,
                search=True,
            )
            try:
                found, usage = self.provider.search_public(query, remaining)
            except Exception:
                budget.report(
                    None,
                    model=self.settings.openai_web_search_model,
                    search=True,
                    reservation=reservation,
                )
                raise
            budget.report(
                normalize_usage(usage),
                model=self.settings.openai_web_search_model,
                search=True,
                reservation=reservation,
            )
            return query, key, found

        candidates = []
        with ThreadPoolExecutor(max_workers=self.settings.agent_search_concurrency) as pool:
            futures = [
                pool.submit(copy_context().run, search, query, key) for query, key in queries
            ]
            for future in as_completed(futures):
                try:
                    query, key, found = future.result()
                    records.append(
                        {
                            "tool": "web_search",
                            "status": "succeeded",
                            "query_hash": key,
                            "candidate_count": len(found),
                        }
                    )
                    candidates.extend((candidate, query, key) for candidate in found[:12])
                except Exception as exc:
                    limitations.append("Search unavailable: " + type(exc).__name__)
                    records.append(
                        {"tool": "web_search", "status": "failed", "error_type": type(exc).__name__}
                    )

        unique = {}
        for candidate, query, key in candidates:
            url = candidate.get("url", "")
            if public_https_url(url):
                unique.setdefault(canonical_url(url), (candidate, query, key))
        ordered = sorted(unique.values(), key=lambda x: authority(x[0]["url"])[2], reverse=True)
        with budget.lock:
            count = min(len(ordered), self.settings.agent_max_documents - budget.documents)
            ordered = ordered[: max(0, count)]
            budget.documents += len(ordered)

        def fetch_one(candidate, query, key):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            source = self.fetcher.read(candidate, remaining)
            source = copy.deepcopy(source)
            origin, jurisdiction, _ = authority(source["url"])
            q_terms = terms(query)
            usable = []
            for p in source["passages"]:
                if is_generic_index_or_snippet(p, q_terms):
                    continue
                p_hash = "sha256:" + hashlib.sha256(p["text"].encode("utf-8")).hexdigest()
                p.update(
                    jurisdiction=jurisdiction,
                    source_type=origin,
                    verification_status="origin_checked_applicability_pending",
                    origin_verified=origin == "indian_official",
                    passage_extracted=True,
                    applicability_checked=False,
                    treatment_checked=False,
                    content_hash=p_hash,
                    generic_snippet=False,
                    publication_date=p.get("publication_date"),
                    effective_date=p.get("effective_date"),
                    limitations=p.get("limitations", "")
                    + " Current legal applicability, completeness and subsequent judicial treatment require claim-specific assessment.",
                )
                usable.append(p)
            per_source = self.settings.agent_passages_per_source
            selected = rank_passages(usable, query, per_source, per_source=per_source)
            if not selected:
                raise ValueError("No relevant extracted passage")
            source["passages"] = selected
            self.repository.save(
                state["owner_id"], state["conversation_id"], state["request_id"], source
            )
            return key, selected

        fetched = {}
        groups = {}
        for candidate in ordered:
            groups.setdefault(urlparse(candidate[0]["url"]).hostname, []).append(candidate)

        def fetch_group(group):
            outcomes = []
            for item in group:
                try:
                    outcomes.append((fetch_one(*item), None))
                except Exception as exc:
                    outcomes.append((None, type(exc).__name__))
            return outcomes

        with ThreadPoolExecutor(max_workers=self.settings.agent_fetch_concurrency) as pool:
            futures = [
                pool.submit(copy_context().run, fetch_group, group) for group in groups.values()
            ]
            for future in as_completed(futures):
                for outcome, error in future.result():
                    if error:
                        limitations.append("Source extraction unavailable: " + error)
                        continue
                    key, selected = outcome
                    fetched.setdefault(key, []).extend(selected)
                    records.append(
                        {
                            "tool": "source_fetch",
                            "status": "succeeded",
                            "source_ids": sorted({p["source_id"] for p in selected}),
                        }
                    )
        for key, selected in fetched.items():
            self.cache.put(key, selected)
            passages.extend(selected)
        selected = rank_passages(
            passages,
            " ".join(q.query for q in request.questions),
            self.settings.agent_max_passages,
            per_source=self.settings.agent_passages_per_source,
        )
        return {
            "status": "candidates_available" if selected else "no_supporting_evidence",
            "evidence": selected,
            "limitations": list(dict.fromkeys(limitations)),
            "tool_records": records,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "budget": budget.snapshot(),
        }
