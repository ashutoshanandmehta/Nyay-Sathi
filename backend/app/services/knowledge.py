import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.schemas.models import CaseMemory

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_PATH = ROOT / "data" / "knowledge" / "consumer_support_v1.json"


class SharedKnowledgeService:
    """Loads reviewed public playbooks separately from private case data and Chroma."""

    def __init__(self, path: Path = DEFAULT_KNOWLEDGE_PATH):
        self.path = path
        self.data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    def public_payload(self) -> dict[str, Any]:
        """Return the public, non-user-specific knowledge catalogue for inspection."""
        return deepcopy(self.data)

    def layer_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "applicable_law",
                "label": "Applicable law and official guidance",
                "count": None,
                "storage": "source register + vector index",
            },
            {
                "id": "procedures",
                "label": "Procedural routes",
                "count": len(self.data.get("procedures", [])),
                "storage": "versioned playbook",
            },
            {
                "id": "intake_playbooks",
                "label": "Intake playbooks",
                "count": len(self.data.get("intake_playbooks", [])),
                "storage": "versioned playbook",
            },
            {
                "id": "evidence_playbooks",
                "label": "Evidence playbooks",
                "count": len(self.data.get("evidence_playbooks", [])),
                "storage": "versioned playbook",
            },
            {
                "id": "templates",
                "label": "Drafting structures",
                "count": len(self.data.get("templates", [])),
                "storage": "template collection",
            },
            {
                "id": "selected_judgments",
                "label": "Curated judgments",
                "count": len(self.data.get("selected_judgments", [])),
                "storage": "register + selected vector passages",
            },
            {
                "id": "lawyer_preparation",
                "label": "Lawyer preparation",
                "count": len(self.data.get("lawyer_preparation", {}).get("pack_sections", [])),
                "storage": "versioned playbook",
            },
            {
                "id": "referrals",
                "label": "Escalation and referrals",
                "count": len(self.data.get("referrals", [])),
                "storage": "versioned official guidance",
            },
        ]

    @staticmethod
    def _issue_from(memory: CaseMemory, message: str) -> str | None:
        fact = memory.facts.get("issue_type")
        if fact:
            return fact.value
        lowered = message.casefold()
        if "not delivered" in lowered or "non-delivery" in lowered or "never arrived" in lowered:
            return "non_delivery"
        if any(word in lowered for word in ("defective", "broken", "damaged", "not working")):
            return "defective_goods"
        if "refund" in lowered or "return" in lowered:
            return "refund_not_received"
        return None

    def guidance_for(self, memory: CaseMemory, current_message: str) -> dict[str, Any]:
        """Select bounded application guidance; this material is explicitly not legal authority."""
        issue = self._issue_from(memory, current_message)
        playbooks = self.data.get("intake_playbooks", [])
        selected = next(
            (p for p in playbooks if issue and issue in p.get("applies_to", [])),
            None,
        )
        evidence = [
            {
                "evidence_type": item["evidence_type"],
                "request": item["request"],
                "may_support": item["may_support"],
                "does_not_automatically_prove": item["does_not_automatically_prove"],
                "preservation": item["preservation"],
            }
            for item in self.data.get("evidence_playbooks", [])
        ]
        return {
            "status": "application_guidance_not_legal_authority",
            "issue_type": issue,
            "intake_playbook": selected,
            "evidence_guidance": evidence,
        }
