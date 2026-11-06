"""Verified, authorized, consistent patches. Semantic approval grants no write power."""

import copy
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.resolution.journey import ComplaintJourneyService
from app.resolution.models import EventType, JourneyProposal
from app.routing.contracts import RequestInterpretation
from app.routing.policy import WorkflowPolicy
from app.schemas.models import CaseFact, CaseMemory, FactStatus, Provenance
from app.services.context_builder import ContextBuilder
from app.services.intake import is_explicit_confirmation, is_explicit_correction


class PatchValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str | None = None
    value: str | None = None
    name: str | None = None
    role: str | None = None
    date: str | None = None
    description: str | None = None
    event_type: EventType | None = None
    recipient: str | None = None


class CasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patch_id: str = Field(min_length=1, max_length=100)
    task_id: str
    operation: Literal[
        "fact",
        "correction",
        "party",
        "location",
        "event",
        "remedy",
        "action",
        "response",
        "outcome",
    ]
    payload: PatchValue
    source_refs: list[str] = Field(min_length=1, max_length=12)
    depends_on: list[str] = Field(default_factory=list, max_length=12)


class PatchVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patch_id: str
    support: Literal["supported", "uncertain", "unsupported"]
    reason: str


class PatchEngine:
    def apply(self, state, patches, verdicts, registry, review_fresh):
        before = CaseMemory.model_validate(state.get("base_memory", state["memory"]))
        memory = before.model_copy(deep=True)
        interpretation = RequestInterpretation.model_validate(state["interpretation"])
        permitted = {t.task_id: t for t in WorkflowPolicy.case_tasks(interpretation, before)}
        judgments = {}
        for item in verdicts:
            judgments.setdefault(item.patch_id, []).append(item)
        decided, pending, accepted, staged = {}, list(patches), [], []
        duplicates = {
            p.patch_id for p in patches if sum(q.patch_id == p.patch_id for q in patches) > 1
        }
        while pending:
            progress = False
            for patch in list(pending):
                if any(dep not in decided for dep in patch.depends_on):
                    continue
                pending.remove(patch)
                progress = True
                decision = "applied"
                reason = "Verified, authorized and state-consistent"
                task = permitted.get(patch.task_id)
                reviews = judgments.get(patch.patch_id, [])
                if not review_fresh or len(reviews) != 1 or reviews[0].support != "supported":
                    decision, reason = "staged", "Independent patch support is unresolved"
                elif not task:
                    decision, reason = (
                        "staged",
                        "Case policy does not authorize this task to modify the case",
                    )
                elif patch.patch_id in duplicates or any(
                    not decided.get(dep) for dep in patch.depends_on
                ):
                    decision, reason = "staged", "Invalid patch identity or dependency"
                elif any(
                    ref not in registry.entries or registry.entries[ref]["kind"] == "public_passage"
                    for ref in patch.source_refs
                ):
                    decision, reason = (
                        "staged",
                        "Fact provenance must be authorized case evidence, not public law",
                    )
                elif task.source_segment_ids and any(
                    registry.entries[ref]["kind"] == "user_report" for ref in patch.source_refs
                ):
                    decision, reason = (
                        "staged",
                        "Use scoped segment provenance instead of the whole message",
                    )
                else:
                    # Segment-scoped tasks cannot write using an unrelated segment.
                    referenced = {
                        r.removeprefix("segment:")
                        for r in patch.source_refs
                        if r.startswith("segment:")
                    }
                    if referenced and not referenced <= set(task.source_segment_ids):
                        decision, reason = (
                            "staged",
                            "Source segment is outside the task's case scope",
                        )
                    elif not self._apply_one(memory, patch, state, registry):
                        decision, reason = (
                            "staged",
                            "Material ambiguity, missing fields or unsupported transition",
                        )
                decided[patch.patch_id] = decision == "applied"
                record = {
                    "patch": patch.model_dump(mode="json"),
                    "decision": decision,
                    "reason": reason,
                }
                (accepted if decision == "applied" else staged).append(record)
            if not progress:
                for patch in pending:
                    staged.append(
                        {
                            "patch": patch.model_dump(mode="json"),
                            "decision": "staged",
                            "reason": "Missing or cyclic dependency",
                        }
                    )
                break
        if memory.model_dump() != before.model_dump():
            if before.domain == "unknown" and accepted:
                memory.domain = permitted[accepted[0]["patch"]["task_id"]].domain
            memory.version = before.version + 1
        return (
            memory,
            accepted,
            staged,
            ContextBuilder.rolling_summary(memory) if accepted else state.get("base_summary", ""),
        )

    @staticmethod
    def _apply_one(memory, patch, state, registry):
        value = patch.payload
        # The runtime constructs provenance; models cannot name another owner/message.
        provenance = []
        for ref in patch.source_refs:
            entry = registry.entries[ref]
            if entry["kind"] in {"user_report", "message_segment"}:
                provenance.append(
                    Provenance(
                        source_type="message", source_id=entry["source_id"], span=entry.get("span")
                    )
                )
            elif entry["kind"] == "document_statement":
                provenance.append(
                    Provenance(
                        source_type="document", source_id=entry["id"], page=entry.get("page")
                    )
                )
            elif entry["kind"] == "case_fact":
                provenance.extend(Provenance.model_validate(p) for p in entry.get("provenance", []))
        if not provenance:
            return False
        status = (
            FactStatus.DOCUMENT
            if all(p.source_type == "document" for p in provenance)
            else FactStatus.ALLEGED
        )
        if patch.operation in {"fact", "correction"}:
            if not value.key or value.value is None:
                return False
            old = memory.facts.get(value.key)
            if old and old.value != value.value:
                if patch.operation != "correction" or not is_explicit_correction(
                    state["current_message"]
                ):
                    return False
                old.previous_values.append(
                    {
                        "value": old.value,
                        "changed_by": state["message_id"],
                        "changed_at": datetime.now(UTC).isoformat(),
                        "confirmation_status": "explicit_correction",
                    }
                )
                old.value, old.status = value.value, FactStatus.CONFIRMED
                old.provenance.extend(provenance)
            elif not old:
                memory.facts[value.key] = CaseFact(
                    key=value.key, value=value.value, status=status, provenance=provenance
                )
            elif (
                is_explicit_confirmation(state["current_message"])
                and value.key in memory.last_proposed_fact_keys
            ):
                old.status = FactStatus.CONFIRMED
                old.provenance.extend(provenance)
            memory.last_proposed_fact_keys = list(
                dict.fromkeys(memory.last_proposed_fact_keys + [value.key])
            )
        elif patch.operation == "remedy":
            if not value.value or (
                memory.requested_remedy
                and memory.requested_remedy != value.value
                and not is_explicit_correction(state["current_message"])
            ):
                return False
            memory.requested_remedy = value.value
            memory.requested_remedy_provenance.extend(provenance)
        else:
            record = {k: v for k, v in value.model_dump().items() if v is not None}
            record.update(
                status=status.value,
                source_id=provenance[0].source_id,
                source_type=provenance[0].source_type,
            )
            if patch.operation == "party":
                if not value.name or not value.role:
                    return False
                target = memory.parties
            elif patch.operation == "location":
                if not value.value:
                    return False
                target = memory.locations
            elif patch.operation in {"event", "response"}:
                if not value.description:
                    return False
                target = memory.events if patch.operation == "event" else memory.responses_received
                if patch.operation == "event" and value.event_type:
                    # Typed, independently supported proposals enter the existing
                    # append-only journey service, never overwrite prior events.
                    source = provenance[0]
                    ComplaintJourneyService().apply(
                        memory.journey,
                        [
                            JourneyProposal(
                                event_type=value.event_type,
                                description=value.description,
                                recipient=value.recipient,
                                occurred_at=value.date,
                                source_type=source.source_type,
                                source_id=source.source_id,
                                page=source.page,
                            )
                        ],
                        message_id=state["message_id"],
                        evidence=state.get("context", {}).get("relevant_evidence", []),
                        source_text=" ".join(
                            registry.entries[r]["text"] for r in patch.source_refs
                        ),
                    )
            elif patch.operation == "action":
                if not value.description:
                    return False
                source = " ".join(registry.entries[r]["text"] for r in patch.source_refs)
                if not re.search(
                    r"\b(?:i|we)\s+(?:(?:have|had|already|also)\s+)*(?:complained|filed|sent|emailed|called|contacted|paid|returned|submitted|requested|received)\b|\bmaine\b|मैंने|हमने",
                    source,
                    re.I,
                ) or re.search(
                    r"\b(?:if i|i should|i might|i will|i haven't|i have not|i never)\b",
                    source,
                    re.I,
                ):
                    return False
                if value.description not in memory.actions_completed:
                    memory.actions_completed.append(value.description)
                    memory.action_provenance[value.description] = provenance
                return True
            elif patch.operation == "outcome":
                if not value.description:
                    return False
                target = memory.outcomes
                record = value.description
            else:
                return False
            if record not in target:
                target.append(copy.deepcopy(record))
        return True
