"""Legal Knowledge Factory: audited proposition-to-source mappings with provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "knowledge"


class LegalProposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposition_id: str = Field(min_length=4, max_length=120)
    proposition_text: str = Field(min_length=20, max_length=3000)
    domain: str = Field(min_length=2, max_length=80)
    jurisdiction: str = Field(min_length=2, max_length=80)
    authority: str = Field(min_length=2, max_length=200)
    source_title: str | None = Field(default=None, max_length=240)
    source_id: str = Field(min_length=2, max_length=120)
    source_url: str = Field(min_length=8, max_length=500)
    exact_passage: str = Field(min_length=20, max_length=4000)
    locator: str = Field(min_length=2, max_length=300)
    effective_date: str | None = None
    commencement_date: str | None = None
    amendments_and_supersession: str = ""
    factual_conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    scenario_tags: list[str] = Field(default_factory=list)
    judicial_treatment_status: str = "pending_review"
    acquired_at: str
    last_reviewed_at: str
    automated_review_status: Literal["verified", "pending", "failed"] = "pending"
    human_review_status: Literal[
        "editor_approved", "pending_editorial_review", "superseded", "rejected"
    ] = "pending_editorial_review"
    source_hierarchy_tier: int = Field(default=3, ge=1, le=5)
    keywords: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passage_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.exact_passage.encode("utf-8")).hexdigest()

    @property
    def is_certified_for_current_law(self) -> bool:
        return (
            self.automated_review_status == "verified"
            and self.human_review_status == "editor_approved"
            and self.judicial_treatment_status not in {"overruled", "superseded", "repealed"}
        )

    def to_evidence_passage(self) -> dict[str, Any]:
        warnings = []
        if self.amendments_and_supersession:
            warnings.append(self.amendments_and_supersession)
        if self.exceptions:
            warnings.append("Exceptions: " + "; ".join(self.exceptions))
        warnings.append(f"Treatment: {self.judicial_treatment_status}.")
        clean_title = self.source_title or self.authority
        return {
            "passage_id": self.proposition_id,
            "source_id": self.source_id,
            "title": clean_title,
            "locator": self.locator,
            "text": f"{self.proposition_text}\n\nExact official passage: {self.exact_passage}",
            "canonical_url": self.source_url,
            "retrieved_at": self.last_reviewed_at,
            "limitations": " ".join(warnings),
            "origin": "certified_proposition",
            "content_hash": self.passage_hash,
            "verification_status": "editor_certified"
            if self.is_certified_for_current_law
            else "pending_editorial_review",
            "source_type": "indian_official",
            "jurisdiction": self.jurisdiction,
            "publication_date": self.commencement_date,
            "effective_date": self.effective_date,
            "origin_verified": True,
            "certified_proposition": self.is_certified_for_current_law,
            "source_hierarchy_tier": self.source_hierarchy_tier,
            "factual_conditions": self.factual_conditions,
            "exceptions": self.exceptions,
            "scenario_tags": self.scenario_tags,
            "amendment_warning": self.amendments_and_supersession,
            "judicial_treatment_status": self.judicial_treatment_status,
            "domain": self.domain,
        }


class LegalKnowledgeFactory:
    """Loads editor-certified propositions and enforces current-law certification boundaries."""

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_ROOT / "certified_propositions_v1.json")
        raw = json.loads(self.path.read_text()) if self.path.exists() else []
        self.propositions: list[LegalProposition] = [
            LegalProposition.model_validate(item) for item in raw
        ]
        self._by_id = {p.proposition_id: p for p in self.propositions}

    def certified(
        self, *, jurisdiction: str | None = None, domain: str | None = None
    ) -> list[LegalProposition]:
        out = [p for p in self.propositions if p.is_certified_for_current_law]
        if jurisdiction:
            wanted = {jurisdiction.casefold(), "india", "central"}
            out = [p for p in out if p.jurisdiction.casefold() in wanted]
        if domain:
            out = [
                p
                for p in out
                if p.domain == domain
                or p.domain in {"constitutional_urgent", "cyber_fraud"}
            ]
        return out

    def get(self, proposition_id: str) -> LegalProposition | None:
        return self._by_id.get(proposition_id)

    def summary(self) -> dict[str, Any]:
        certified_count = sum(1 for p in self.propositions if p.is_certified_for_current_law)
        return {
            "total_propositions": len(self.propositions),
            "certified_propositions": certified_count,
            "domains": sorted({p.domain for p in self.propositions}),
            "urgent_pack_ids": [
                p.proposition_id
                for p in self.propositions
                if p.domain in {"constitutional_urgent", "criminal", "cyber_fraud"}
            ],
        }
