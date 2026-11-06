"""The application owns source text; interpretation only references it."""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from app.routing.contracts import Contract, EntityMention, RequestInterpretation, TaskIntent


def segment_message(text, limit=1200):
    segments = []
    for match in re.finditer(r"[^\n]+", text):
        start, end = match.span()
        while start < end:
            stop = min(start + limit, end)
            if stop < end:
                boundary = text.rfind(" ", start + limit // 2, stop)
                if boundary > start:
                    stop = boundary
            if text[start:stop].strip():
                segments.append(
                    {
                        "id": f"seg-{len(segments) + 1}",
                        "start": start,
                        "end": stop,
                        "text": text[start:stop],
                    }
                )
            start = stop if stop == end else stop + int(text[stop : stop + 1] == " ")
    return segments


IntentType = TaskIntent.model_fields["intent"].annotation
DomainType = TaskIntent.model_fields["domain"].annotation
CaseLinkType = TaskIntent.model_fields["case_link"].annotation
RiskType = TaskIntent.model_fields["risk_level"].annotation


class ReferencedTask(Contract):
    task_id: str = Field(pattern=r"^task-[1-8]$")
    source_segment_ids: list[str] = Field(min_length=1, max_length=24)
    intent: IntentType
    domain: DomainType
    relationship: str | None
    entities: list[EntityMention]
    case_link: CaseLinkType
    requires_research: bool
    requires_case_update: bool
    risk_level: RiskType
    uncertainty: list[str]
    public_query: str | None
    needs_early_extraction: bool
    extraction_reason: str | None


class SegmentInterpretation(Contract):
    schema_version: Literal["request-v2"] = "request-v2"
    tasks: list[ReferencedTask] = Field(min_length=1, max_length=8)
    clarification_needed: bool


def resolve_interpretation(data, message):
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    segments = segment_message(message)
    available = {s["id"]: s for s in segments}
    tasks, rejected = [], []
    raw_tasks = data.get("tasks", [])
    if not isinstance(raw_tasks, list) or not 1 <= len(raw_tasks) <= 8:
        raise ValueError("Invalid task envelope")
    for raw in raw_tasks:
        try:
            task = ReferencedTask.model_validate(raw)
            refs = set(task.source_segment_ids)
            if (
                not refs <= available.keys()
                or sum(isinstance(t, dict) and t.get("task_id") == task.task_id for t in raw_tasks)
                != 1
            ):
                raise ValueError("Unknown reference or duplicate task identity")
            ordered = [s for s in segments if s["id"] in refs]
            value = task.model_dump(mode="json")
            value["source_text"] = "\n".join(s["text"] for s in ordered)
            tasks.append(TaskIntent.model_validate(value))
        except (ValidationError, ValueError, TypeError):
            rejected.append(
                {
                    "code": "invalid_task_reference_or_contract",
                    "task_id": raw.get("task_id") if isinstance(raw, dict) else None,
                    "contract_hash": hashlib.sha256(
                        json.dumps(raw, sort_keys=True).encode()
                    ).hexdigest(),
                }
            )
    if not tasks:
        raise ValueError("No independently valid tasks")
    links = {t.case_link for t in tasks}
    return RequestInterpretation(
        schema_version="request-v2",
        tasks=tasks,
        case_relevance=next(iter(links)) if len(links) == 1 else "mixed",
        clarification_needed=bool(data.get("clarification_needed") or rejected),
        invalid_tasks=rejected,
    )


PROMPT = Path(__file__).parents[1] / "prompts/v2/interpretation.md"
