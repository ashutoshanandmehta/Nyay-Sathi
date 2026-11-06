"""Concurrent, bounded research reusing V1's safe downloader and source extraction."""

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

from app.agent.contracts import ResearchRequest
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


def terms(text):
    stop = {
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
    return {
        w
        for w in re.findall(r"[\w\u0900-\u097f]+", text.casefold())
        if len(w) > 2 and w not in stop
    }


def rank_passages(passages, query, limit):
    wanted = terms(query)
    scored = []
    for p in passages:
        overlap = len(wanted & terms(p["text"]))
        if not overlap:
            continue
        _, _, weight = authority(p["canonical_url"])
        score = overlap / max(1, len(wanted)) * 10 + weight
        if p.get("effective_date"):
            score += 0.2  # Known date is useful metadata, not proof of current law.
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected, hashes, per_source = [], set(), {}
    for _, passage in scored:
        digest = hashlib.sha256(passage["text"].encode()).hexdigest()
        key = passage["source_id"]
        if digest in hashes or per_source.get(key, 0) >= 2:
            continue
        selected.append(passage)
        hashes.add(digest)
        per_source[key] = per_source.get(key, 0) + 1
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
        self, settings, retriever, provider=None, fetcher=None, repository=None, cache=None
    ):
        self.settings, self.retriever = settings, retriever
        self.provider = provider or OfficialSearchProvider(settings)
        self.fetcher = fetcher or SafeSourceFetcher(settings, url_policy=public_https_url)
        self.repository = repository or ResearchRepository(settings)
        self.cache = cache or EvidenceCache(settings.database_path, settings.web_cache_ttl_seconds)

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
                cached = None if request.fresh_required else self.cache.get(key)
                if cached:
                    passages.extend(cached)
                    records.append({"tool": "evidence_cache", "status": "hit", "query_hash": key})
                else:
                    queries.append((query, key))
                # Local passages are candidates only and must match the issue, not a domain keyword gate.
                # No vector/embedding call is made here.
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
                        if 0 <= age <= 30 and len(terms(query) & terms(p["text"])) >= 2:
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
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            # Reserve final agent continuation and independent review before paid discovery.
            budget.reserve(
                self.settings.openai_web_search_model,
                len(query.encode()) + 2000,
                reserve=2,
                search=True,
            )
            try:
                found, usage = self.provider.search_public(query, remaining)
            except Exception:
                budget.report(None, model=self.settings.openai_web_search_model, search=True)
                raise
            budget.report(
                normalize_usage(usage), model=self.settings.openai_web_search_model, search=True
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

        # Deduplicate before downloading; prefer Indian primary origins without excluding new hosts.
        unique = {}
        for candidate, query, key in candidates:
            url = candidate.get("url", "")
            if public_https_url(url):
                unique.setdefault(canonical_url(url), (candidate, query, key))
        ordered = sorted(unique.values(), key=lambda x: authority(x[0]["url"])[2], reverse=True)
        with budget.lock:
            count = min(len(ordered), self.settings.agent_max_documents - budget.documents, 4)
            ordered = ordered[: max(0, count)]
            budget.documents += len(ordered)

        def fetch_one(candidate, query, key):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            source = self.fetcher.read(candidate, remaining)
            source = copy.deepcopy(source)
            origin, jurisdiction, _ = authority(source["url"])
            for p in source["passages"]:
                p.update(
                    jurisdiction=jurisdiction,
                    source_type=origin,
                    verification_status="origin_checked_applicability_pending",
                    origin_verified=origin == "indian_official",
                    passage_extracted=True,
                    applicability_checked=False,
                    treatment_checked=False,
                    publication_date=p.get("publication_date"),
                    effective_date=p.get("effective_date"),
                    limitations=p.get("limitations", "")
                    + " Current legal applicability, completeness and subsequent judicial treatment require claim-specific assessment.",
                )
            selected = rank_passages(source["passages"], query, 3)
            if not selected:
                raise ValueError("No relevant extracted passage")
            source["passages"] = selected
            self.repository.save(
                state["owner_id"], state["conversation_id"], state["request_id"], source
            )
            return key, selected

        fetched = {}
        # Per-host groups execute sequentially, while different hosts may overlap.
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
            passages, " ".join(q.query for q in request.questions), self.settings.agent_max_passages
        )
        return {
            "status": "candidates_available" if selected else "no_supporting_evidence",
            "evidence": selected,
            "limitations": list(dict.fromkeys(limitations)),
            "tool_records": records,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "budget": budget.snapshot(),
        }
