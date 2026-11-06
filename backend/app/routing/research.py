"""Public task research, separate from consumer eligibility and private evidence."""

import hashlib
import ipaddress
import re
import time
from urllib.parse import urlparse

from app.routing.policy import CapabilityRegistry, PublicQueryPolicy
from app.services.progress import publisher
from app.services.web_research import (
    OfficialSearchProvider,
    ResearchRepository,
    SafeSourceFetcher,
    add_usage,
)


def public_https_url(url):
    """Network permission is distinct from source authority. DNS is checked in fetch."""
    try:
        value = urlparse(url)
        if (
            len(url) > 2048
            or value.scheme != "https"
            or not value.hostname
            or value.username
            or value.password
            or value.port not in {None, 443}
        ):
            return False
        host = value.hostname.casefold()
        if (
            host == "localhost"
            or host.endswith((".local", ".localhost", ".internal"))
            or "." not in host
        ):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except ValueError:
        return False


class TaskResearchService:
    def __init__(self, settings, provider=None, fetcher=None, repository=None):
        self.settings = settings
        self.provider = provider or OfficialSearchProvider(settings)
        self.fetcher = fetcher or SafeSourceFetcher(settings, url_policy=public_https_url)
        self.repository = repository or ResearchRepository(settings)

    def run(self, task, state, *, documents_remaining):
        started = time.monotonic()
        record = {
            "tool": "web_search",
            "task_id": task.task_id,
            "status": "not_run",
            "source_ids": [],
        }
        calls = state.get("model_calls", 0)
        usage = state.get("token_usage", {})
        passages = []
        status = CapabilityRegistry(self.settings).snapshot(calls)["web_search"]["status"]
        if status != "available":
            record["status"] = status
            return record, passages, calls, usage
        if documents_remaining <= 0:
            record["status"] = "budget_exhausted"
            return record, passages, calls, usage
        try:
            query = PublicQueryPolicy.validate(task.public_query, state.get("context", {}))
        except ValueError:
            record["status"] = "policy_restricted"
            return record, passages, calls, usage
        calls += 1
        callback = publisher.get()
        if callback:
            callback({"stage": "web_search", "status": "running"})
        try:
            candidates, extra = self.provider.search_public(
                query, self.settings.web_research_timeout_seconds
            )
            usage = add_usage(usage, extra)
            record["counts"] = {
                **extra.get("discovery_counts", {}),
                "valid_url_count": 0,
                "fetched_source_count": 0,
                "official_origin_count": 0,
                "relevant_fetched_candidate_count": 0,
            }
            record["search_completed"] = True
            record["query"] = query
            record["candidate_count"] = len(candidates)
            record["status"] = "no_supporting_results"
            seen = set()
            errors = []
            rejected = []
            candidate_metadata = []
            for candidate in candidates:
                if len(seen) >= documents_remaining:
                    break
                url = candidate.get("url", "")
                candidate_metadata.append(
                    {
                        "host": urlparse(url).hostname,
                        "url_hash": hashlib.sha256(url.encode()).hexdigest(),
                    }
                )
                if url in seen or not public_https_url(url):
                    rejected.append(
                        {
                            "url_hash": hashlib.sha256(url.encode()).hexdigest(),
                            "reason": "duplicate_or_network_policy",
                        }
                    )
                    continue
                record["counts"]["valid_url_count"] += 1
                remaining = self.settings.web_research_timeout_seconds - (
                    time.monotonic() - started
                )
                if remaining <= 0:
                    errors.append("TimeoutError")
                    break
                seen.add(url)
                try:
                    if callback:
                        callback({"stage": "web_fetch", "status": "running"})
                    source = self.fetcher.read(candidate, remaining)
                    record["counts"]["fetched_source_count"] += 1
                    host = urlparse(source["url"]).hostname or ""
                    official = host.endswith(
                        (".gov.in", ".nic.in", ".gov", ".sci.gov.in")
                    ) or host in {
                        "sci.gov.in",
                        "rbi.org.in",
                        "www.rbi.org.in",
                    }
                    record["counts"]["official_origin_count"] += int(official)
                    for passage in source["passages"]:
                        if passage.get("locator", "").startswith("Official webpage"):
                            passage["locator"] = f"Public webpage ({source['url']})"
                        passage.update(
                            source_type="official_public" if official else "public_candidate",
                            verification_status="official_origin_pending_answer_review"
                            if official
                            else "unverified_public_source",
                            jurisdiction=None,
                            publication_date=None,
                            effective_date=None,
                            task_id=task.task_id,
                            applicable_task_ids=[task.task_id],
                            task_domain=task.domain,
                            limitations="Fetched public text, not verified legal applicability or organization identity. Unknown jurisdiction/effective dates remain unknown; independent review required.",
                        )
                    # Snippets are never promoted. Keep only fetched passages matching query terms.
                    terms = {
                        t for t in re.findall(r"[\w\u0900-\u097f]+", query.casefold()) if len(t) > 3
                    }
                    ranked = sorted(
                        source["passages"],
                        key=lambda p: sum(t in p["text"].casefold() for t in terms),
                        reverse=True,
                    )
                    supported = [
                        p for p in ranked if any(t in p["text"].casefold() for t in terms)
                    ][:3]
                    if not supported:
                        rejected.append(
                            {
                                "url_hash": hashlib.sha256(source["url"].encode()).hexdigest(),
                                "reason": "no_relevant_fetched_passage",
                            }
                        )
                        continue
                    record["counts"]["relevant_fetched_candidate_count"] += 1
                    self.repository.save(
                        state["owner_id"], state["conversation_id"], state["message_id"], source
                    )
                    passages.extend(supported)
                    record["source_ids"].append(source["source_id"])
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    rejected.append(
                        {
                            "url_hash": hashlib.sha256(url.encode()).hexdigest(),
                            "reason": "fetch_failed",
                            "error_type": type(exc).__name__,
                        }
                    )
            record["documents_attempted"] = len(seen)
            record["status"] = (
                "succeeded"
                if passages
                else "execution_failed"
                if errors
                else "no_supporting_results"
            )
            if errors:
                record["errors"] = errors  # Types only; no upstream credential/request text.
            record["candidate_rejections"] = rejected
            record["candidate_metadata"] = candidate_metadata
            record["applicability_status"] = "pending_claim_review"
        except Exception as exc:
            usage = add_usage(usage, getattr(exc, "token_usage", {}))
            record.update(status="execution_failed", error_type=type(exc).__name__)
        record["latency_ms"] = round((time.monotonic() - started) * 1000)
        return record, passages, calls, usage
