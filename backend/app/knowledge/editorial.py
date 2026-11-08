"""Legal editorial review workflow and audited multilingual packs (EN / HI / Hinglish)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db import now


class EditorialProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposition_id: str = Field(min_length=4, max_length=120)
    domain: str = Field(min_length=2, max_length=80)
    jurisdiction: str = Field(min_length=2, max_length=80)
    proposition_text: str = Field(min_length=20, max_length=3000)
    source_url: str = Field(min_length=8, max_length=500)
    exact_passage: str = Field(min_length=20, max_length=4000)
    locator: str = Field(min_length=2, max_length=300)
    effective_date: str | None = None
    amendments_and_supersession: str = ""


class EditorialDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=2, max_length=120)
    bar_enrollment_ref: str = Field(min_length=3, max_length=80)
    decision: Literal["editor_approved", "superseded", "rejected"]
    notes: str = Field(default="", max_length=1000)


AUDITED_LANGUAGE_PACKS: dict[str, dict[str, Any]] = {
    "en": {
        "language_code": "en",
        "label": "English (India)",
        "audit_status": "audited_core_pack_v1",
        "native_legal_review": "reviewed_terminology_v1",
        "voice_ocr_tested": True,
        "screen_reader_low_bandwidth_ready": True,
        "glossary": {
            "pre_litigation": "Pre-litigation grievance (before filing a formal court/commission case)",
            "limitation_period": "Statutory time limit to file a formal complaint",
            "user_allegation": "Reported by you (not yet independently verified)",
            "certified_proposition": "Verified Indian legal source",
        },
        "safety_phrasing_note": "Direct, calm, non-confrontational protective steps first.",
    },
    "hi": {
        "language_code": "hi",
        "label": "हिन्दी (भारत)",
        "audit_status": "audited_core_pack_v1",
        "native_legal_review": "reviewed_terminology_v1",
        "voice_ocr_tested": True,
        "screen_reader_low_bandwidth_ready": True,
        "glossary": {
            "pre_litigation": "मुकदमे से पहले शिकायत निवारण (प्रारंभिक शिकायत प्रक्रिया)",
            "limitation_period": "शिकायत दर्ज करने की वैधानिक समय-सीमा (परिसीमा काल)",
            "user_allegation": "आपके द्वारा बताई गई जानकारी",
            "certified_proposition": "सत्यापित भारतीय विधिक स्रोत (हिन्दी प्रस्तुति अनुवाद है; मूल राजपत्र पाठ प्रभावी है)",
        },
        "safety_phrasing_note": "शांत, गैर-टकराव वाली सुरक्षा सलाह; संकट की स्थिति में तुरंत भरोसेमंद व्यक्ति या 112 की जानकारी।",
    },
    "hinglish": {
        "language_code": "hinglish",
        "label": "Hinglish (Conversational)",
        "audit_status": "audited_core_pack_v1",
        "native_legal_review": "reviewed_terminology_v1",
        "voice_ocr_tested": True,
        "screen_reader_low_bandwidth_ready": True,
        "glossary": {
            "pre_litigation": "Formal case file karne se pehle ki official शिकायत / grievance route",
            "limitation_period": "Complaint file karne ki kanooni time-limit",
            "user_allegation": "Aapke bataye gaye facts",
            "certified_proposition": "Verified Indian legal source",
        },
        "safety_phrasing_note": "Clear everyday phrasing without legal jargon; non-confrontational safety first.",
    },
}


class LanguagePackRegistry:
    """Audited language packs; blocks unaudited raw machine-translation locales."""

    @staticmethod
    def list_packs() -> list[dict[str, Any]]:
        return list(AUDITED_LANGUAGE_PACKS.values())

    @staticmethod
    def get_pack(code: str) -> dict[str, Any]:
        return AUDITED_LANGUAGE_PACKS.get(code, AUDITED_LANGUAGE_PACKS["en"])


class EditorialRegistry:
    """Persists lawyer editorial queue items for certifying legal propositions."""

    def __init__(self, database):
        self.db = database
        with self.db.connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS editorial_propositions (
                    item_id TEXT PRIMARY KEY,
                    proposition_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    decision_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    def submit(self, proposal: EditorialProposal) -> dict[str, Any]:
        item_id = "ed-" + uuid.uuid4().hex[:12]
        ts = now()
        record = {
            "item_id": item_id,
            "proposition_id": proposal.proposition_id,
            "status": "pending_editorial_review",
            "proposal": proposal.model_dump(mode="json"),
            "decision": None,
            "created_at": ts,
            "updated_at": ts,
        }
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO editorial_propositions VALUES (?, ?, ?, ?, NULL, ?, ?)",
                (
                    item_id,
                    proposal.proposition_id,
                    "pending_editorial_review",
                    json.dumps(record["proposal"]),
                    ts,
                    ts,
                ),
            )
        return record

    def decide(self, item_id: str, decision: EditorialDecision) -> dict[str, Any]:
        ts = now()
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM editorial_propositions WHERE item_id=?", (item_id,)
            ).fetchone()
            if not row:
                raise KeyError("Editorial item not found")
            conn.execute(
                "UPDATE editorial_propositions SET status=?, decision_json=?, updated_at=? WHERE item_id=?",
                (decision.decision, json.dumps(decision.model_dump(mode="json")), ts, item_id),
            )
        return {
            "item_id": item_id,
            "proposition_id": row["proposition_id"],
            "status": decision.decision,
            "proposal": json.loads(row["proposal_json"]),
            "decision": decision.model_dump(mode="json"),
            "updated_at": ts,
        }

    def list_items(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = (
                conn.execute(
                    "SELECT * FROM editorial_propositions WHERE status=? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
                if status
                else conn.execute(
                    "SELECT * FROM editorial_propositions ORDER BY updated_at DESC"
                ).fetchall()
            )
        return [
            {
                "item_id": r["item_id"],
                "proposition_id": r["proposition_id"],
                "status": r["status"],
                "proposal": json.loads(r["proposal_json"]),
                "decision": json.loads(r["decision_json"]) if r["decision_json"] else None,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
