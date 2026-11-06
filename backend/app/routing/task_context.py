"""Trusted task execution policies, derived from interpretation by application code."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    domain: str
    intent: str
    risk_level: str
    allowed_corpora: tuple[str, ...]
    research_policy: str = "public_candidates_require_claim_review"
    persistence_policy: str = "proposal_only"

    @classmethod
    def for_task(cls, task):
        return cls(
            task.task_id,
            task.domain,
            task.intent,
            task.risk_level,
            ("official_consumer",) if task.domain == "consumer" else (),
        )

    def payload(self):
        return asdict(self)


class ApplicabilityPolicy:
    @staticmethod
    def cache_recent(passage, max_age_days=30):
        """Acquisition freshness only; this never proves current legal applicability."""
        if passage.get("verification_status") in {
            "stale",
            "conflicting",
            "unverified_public_source",
        }:
            return False
        try:
            checked = datetime.fromisoformat(passage["retrieved_at"].replace("Z", "+00:00")).date()
            return 0 <= (datetime.now(UTC).date() - checked).days <= max_age_days
        except (KeyError, ValueError, TypeError):
            return False

    @staticmethod
    def permits(context, passage):
        if passage.get("origin") != "web" and context.domain != "consumer":
            return False
        # A curated housing judgment is not generally applicable to retail goods.
        if (
            passage.get("source_type") == "judgment"
            or "experion" in passage.get("source_id", "").casefold()
        ):
            return context.intent == "judgment_comparison"
        if passage.get("origin") == "web":
            return context.task_id in passage.get("applicable_task_ids", [passage.get("task_id")])
        return context.domain == "consumer"

    @staticmethod
    def can_share(source_task, destination_task):
        # Identical issue context is required, not merely a similar search string.
        return (
            source_task.domain == destination_task.domain
            and source_task.case_link == destination_task.case_link
            and source_task.case_link in {"new", "existing"}
            and source_task.source_text == destination_task.source_text
        )


class ExecutionBudget:
    def __init__(self, settings, calls):
        self.settings, self.calls = settings, calls

    def permits_research(self):
        return self.calls + 3 <= self.settings.max_model_calls_per_turn

    def permits_repair(self):
        return self.calls + 2 <= self.settings.max_model_calls_per_turn
