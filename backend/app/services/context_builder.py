import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.answers.evidence import strip_citation_markers
from app.schemas.models import CaseMemory
from app.services.evidence import EvidenceSearchService


class ContextBuilder:
    """Builds bounded, provenance-preserving context while the full transcript stays in SQLite."""

    def __init__(self, max_chars: int = 24_000):
        self.max_chars = max_chars

    @staticmethod
    def for_model(memory):
        """Bound long-lived domain history; complete records stay in case storage."""
        result = dict(memory)
        journey = dict(result.get("journey", {}))
        journey["recommendations"] = []  # The current plan is supplied separately.
        for key in ("events", "responses", "commitments", "submissions"):
            journey[key] = journey.get(key, [])[-16:]
        result["journey"] = journey
        result.pop("last_draft_spec", None)
        return result

    def build(
        self,
        *,
        current_message: str,
        memory: CaseMemory,
        summary: str,
        recent_messages: list[dict[str, Any]],
        evidence: list[dict[str, Any]] | None = None,
        pending: str | None = None,
    ) -> dict[str, Any]:
        facts = {
            key: {
                "value": fact.value,
                "status": fact.status.value,
                "provenance": [p.model_dump(mode="json") for p in fact.provenance],
            }
            for key, fact in memory.facts.items()
        }
        relevant_evidence = EvidenceSearchService().search(current_message, evidence or [])
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))
        last_assistant = next((m for m in reversed(recent_messages) if m.get("role") == "assistant"), {})
        last_tasks = last_assistant.get("metadata", {}).get("interpretation", {}).get("tasks", [])
        confirmation_scope = bool(memory.last_proposed_fact_keys and last_tasks and
            last_assistant.get("metadata", {}).get("case_update_allowed") and
            all(t.get("domain") in {"consumer", "employment", "tenancy", "criminal", "other_legal"} for t in last_tasks))
        prior_assistant = [m for m in recent_messages if m.get("role") == "assistant"]
        covered_source_ids: list[str] = []
        delivered_block_types: list[str] = []
        prior_next_actions: list[str] = []
        for msg in prior_assistant:
            meta = msg.get("metadata") or {}
            for src in meta.get("sources") or []:
                sid = src.get("source_id")
                if sid and sid not in covered_source_ids:
                    covered_source_ids.append(sid)
            for blk in meta.get("resolution_blocks") or []:
                bt = blk.get("block_type")
                if bt and bt not in delivered_block_types:
                    delivered_block_types.append(bt)
                for sid in blk.get("source_ids") or []:
                    if sid and sid not in covered_source_ids:
                        covered_source_ids.append(sid)
            na = meta.get("next_action")
            if na and na not in prior_next_actions:
                prior_next_actions.append(na)
        context: dict[str, Any] = {
            "current_message": current_message,
            "case_confirmation_eligible": confirmation_scope,
            "runtime": {
                "current_datetime": ist_now.isoformat(),
                "current_date": ist_now.date().isoformat(),
                "timezone": "Asia/Kolkata",
                "date_rule": "Current time does not resolve an ambiguous historical date and does not determine a legal deadline.",
            },
            "pending_question_or_stage": pending or memory.pending_questions[-3:],
            "confirmed_and_reported_facts": facts,
            "contradictions": memory.contradictions,
            "unknowns": memory.unknowns,
            "parties": memory.parties,
            "locations": memory.locations,
            "requested_remedy": memory.requested_remedy,
            "timeline": memory.events[-12:],
            "actions_completed": memory.actions_completed[-10:],
            "responses_received": memory.responses_received[-10:],
            "correspondence_history": memory.correspondence_history[-10:],
            "questions_for_legal_review": memory.questions_for_legal_review[-10:],
            "urgent_matters": memory.urgent_matters[-6:],
            "complaint_journey": self.for_model(memory.model_dump(mode="json"))["journey"],
            "prior_assistant_coverage": {
                "assistant_turn_count": len(prior_assistant),
                "covered_source_ids": covered_source_ids[:16],
                "delivered_block_types": delivered_block_types,
                "prior_next_actions": prior_next_actions[-3:],
                "evidence_checklist_already_shown": "evidence_checklist" in delivered_block_types,
            },
            "rolling_summary": summary,
            "recent_turns": [
                {
                    "id": m["id"],
                    "role": m["role"],
                    # Citation numbers are per message; the model would otherwise reuse stale ones.
                    "content": (
                        strip_citation_markers(m["content"])
                        if m["role"] == "assistant"
                        else m["content"]
                    )[:3000],
                }
                for m in recent_messages[-10:]
            ],
            "relevant_evidence": relevant_evidence,
        }
        while (
            len(json.dumps(context, ensure_ascii=False)) > self.max_chars
            and context["recent_turns"]
        ):
            context["recent_turns"].pop(0)
        return context

    @staticmethod
    def rolling_summary(memory: CaseMemory) -> str:
        items = [f"Domain: {memory.domain}."]
        if memory.requested_remedy:
            items.append(f"Requested remedy: {memory.requested_remedy}.")
        if memory.journey.submissions:
            items.append(
                "Previous complaint recipients: "
                + "; ".join(s.recipient for s in memory.journey.submissions[-5:])
                + "."
            )
        if memory.journey.outcome != "unknown":
            items.append(
                f"Reported outcome: {memory.journey.outcome}; user satisfaction: {memory.journey.satisfaction}."
            )
        if memory.parties:
            items.append(
                "Parties: "
                + "; ".join(
                    f"{item.get('name', 'unknown')} ({item.get('role', 'role unknown')})"
                    for item in memory.parties[-6:]
                )
                + "."
            )
        if memory.facts:
            rendered = "; ".join(
                f"{k}={v.value} [{v.status.value}]" for k, v in list(memory.facts.items())[:12]
            )
            items.append(f"Facts: {rendered}.")
        if memory.actions_completed:
            items.append("Completed actions: " + "; ".join(memory.actions_completed[-6:]) + ".")
        if memory.responses_received:
            items.append(
                "Responses received: "
                + "; ".join(str(item) for item in memory.responses_received[-4:])
                + "."
            )
        if memory.events:
            items.append(
                "Recent events: "
                + "; ".join(
                    f"{item.get('date') or 'date unknown'}: {item.get('description', '')}"
                    for item in memory.events[-6:]
                )
                + "."
            )
        if memory.contradictions:
            items.append(
                "Unresolved contradictions: "
                + "; ".join(str(x.get("description", x)) for x in memory.contradictions[-4:])
                + "."
            )
        if memory.unknowns:
            items.append("Open questions: " + "; ".join(memory.unknowns[-6:]) + ".")
        if memory.pending_questions:
            items.append(
                "Pending questions: "
                + "; ".join(
                    str(item.get("question", item)) for item in memory.pending_questions[-3:]
                )
                + "."
            )
        return " ".join(items)[:5000]
