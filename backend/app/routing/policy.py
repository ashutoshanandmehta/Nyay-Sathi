"""Policies consume interpretation; model proposals never grant write/tool permission."""

import re

from app.routing.contracts import TaskExecution
from app.routing.interpretation import LEGAL_DOMAINS


class WorkflowPolicy:
    @staticmethod
    def investigate_tasks(interpretation):
        """Extraction may stage facts without granting a case write."""
        return [
            task
            for task in interpretation.tasks
            if task.domain in LEGAL_DOMAINS
            and task.case_link in {"new", "existing", "uncertain"}
            and task.intent not in {"conversation", "clarify"}
            and (task.relationship or task.requires_case_update)
        ]

    @staticmethod
    def plan(interpretation):
        results = []
        for task in sorted(interpretation.tasks, key=lambda t: t.risk_level != "urgent"):
            workflow = (
                "safety"
                if task.risk_level == "urgent" or task.domain in {"health", "animal_health"}
                else "consumer"
                if task.domain == "consumer"
                else "legal_handoff"
                if task.domain in LEGAL_DOMAINS
                else "clarify"
                if task.intent == "clarify"
                else "conversation"
                if task.intent == "conversation"
                else "general"
            )
            results.append(
                TaskExecution(
                    task_id=task.task_id,
                    workflow=workflow,
                    status="clarification_required" if task.case_link == "uncertain" else "ready",
                    research_status="pending" if task.requires_research else "not_required",
                    reason="Interpretation selects assistance, never legal eligibility or permission to submit.",
                )
            )
        return results

    @staticmethod
    def case_tasks(interpretation, memory):
        existing = bool(memory.facts or memory.parties or memory.journey.events or memory.version)
        existing_domain = {
            "unpaid_salary": "employment",
            "landlord_deposit": "tenancy",
            "other_unsupported": "other_legal",
        }.get(memory.domain, memory.domain)
        permitted = [
            task
            for task in interpretation.tasks
            if task.domain in LEGAL_DOMAINS
            and (task.relationship or task.requires_case_update)
            and task.intent not in {"information", "search", "conversation", "clarify"}
            and (not existing or existing_domain in {"unknown", task.domain})
            and (task.case_link == "existing" or (task.case_link == "new" and not existing))
        ]
        if not existing and permitted:
            first_domain = permitted[0].domain
            permitted = [task for task in permitted if task.domain == first_domain]
        return permitted


class CapabilityRegistry:
    def __init__(self, settings):
        self.settings = settings

    def snapshot(self, calls=0):
        search = (
            "disabled"
            if not self.settings.web_research_enabled
            else "configuration_required"
            if not self.settings.ai_configured
            else "budget_exhausted"
            if calls + 3 > self.settings.max_model_calls_per_turn
            else "available"
        )
        return {
            "web_search": {
                "status": search,
                "policy": "public queries; fetched passages required; no personal identifiers",
            },
            "source_fetch": {
                "status": "available",
                "policy": "HTTPS public destinations; bounded downloads; source trust assessed separately",
            },
            "legal_corpus": {
                "status": "available",
                "policy": "approved consumer corpus; no cross-domain authority inference",
            },
            "case_write": {"status": "policy_controlled"},
            "external_submission": {"status": "disabled"},
            "remaining_model_calls": max(0, self.settings.max_model_calls_per_turn - calls),
        }


class PublicQueryPolicy:
    @staticmethod
    def validate(query, context):
        if (
            not query
            or len(query) > 500
            or re.search(
                r"https?://|@|\b\d{5,}\b|₹|\b(?:order|ticket|account|transaction)\s*(?:id|no|number|#|:)",
                query,
                re.I,
            )
        ):
            raise ValueError("Public query contains identifiers or unsupported syntax")
        private = []
        for key, fact in context.get("confirmed_and_reported_facts", {}).items():
            if key not in {"issue_type", "consumer_purpose", "transaction_country"}:
                private.append(str(fact.get("value", "")))
        for party in context.get("parties", []):
            if party.get("role") not in {"seller", "platform", "employer", "service_provider"}:
                private.append(party.get("name", ""))
        current = context.get("current_message", "")
        private.extend(
            match.group(1).strip()
            for match in re.finditer(
                r"(?:my name is|mera naam|मेरा नाम)\s+([^,.!?\n]{3,80})", current, re.I
            )
        )
        if any(
            value and len(value) >= 3 and value.casefold() in query.casefold() for value in private
        ):
            raise ValueError("Public query contains private case data")
        query_words = re.findall(r"\w+", query.casefold())
        for excerpt in context.get("relevant_evidence", []):
            document = " ".join(re.findall(r"\w+", excerpt.get("text", "").casefold()))
            if any(
                " ".join(query_words[i : i + 5]) in document
                for i in range(max(0, len(query_words) - 4))
            ):
                raise ValueError("Public query reproduces private evidence text")
        return query.strip()
