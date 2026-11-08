"""Prepared Lawyer & Legal-Aid Escalation Bundle without hidden model reasoning."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schemas.models import CaseMemory, FactStatus


def build_escalation_bundle(
    *,
    conversation: dict[str, Any],
    memory: CaseMemory,
    summary: str,
    messages: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
    safety_messages: list[dict[str, Any]],
    user_actions: list[dict[str, Any]],
    submission_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble an auditable handoff package for a licensed advocate or legal-aid clinic.

    Strictly excludes raw prompts, hidden chain-of-thought, and encrypted reasoning tokens.
    """
    reasons: list[str] = []
    if safety_messages or memory.domain == "criminal" or memory.urgent_matters:
        reasons.append("Immediate safety, police/officer coercion, or personal liberty concern.")
    if memory.contradictions:
        reasons.append("Material factual contradictions require human verification against originals.")
    if len(memory.unknowns) + len(memory.questions_for_legal_review) >= 2:
        reasons.append("Multiple unresolved factual or legal applicability questions remain open.")

    assistant_msgs = [
        m for m in messages if m.get("role") == "assistant" and m.get("status") == "complete"
    ]
    partial_turns = [
        m for m in assistant_msgs if (m.get("metadata") or {}).get("publication_status") == "partial"
    ]
    if partial_turns:
        reasons.append(
            "At least one legal question had partial source verification and benefits from counsel review."
        )

    consistent_facts: list[dict[str, Any]] = []
    uncertain_facts: list[dict[str, Any]] = []
    for key, item in memory.facts.items():
        status_val = item.status.value if isinstance(item.status, FactStatus) else str(item.status)
        entry = {
            "key": key,
            "value": item.value,
            "status": status_val,
            "provenance": [p.model_dump(mode="json") for p in item.provenance],
            "previous_values": item.previous_values,
        }
        if status_val in {"unknown", "assistant_inference"} or item.previous_values:
            uncertain_facts.append(entry)
        else:
            consistent_facts.append(entry)

    chronology: list[dict[str, Any]] = []
    for ev in memory.journey.events:
        chronology.append(
            {
                "timestamp": ev.occurred_at or ev.recorded_at,
                "kind": ev.event_type.value,
                "actor": ev.recipient or "user_reported",
                "channel": ev.channel,
                "summary": ev.description,
                "status": ev.evidence_status,
                "grounding": "reported_by_user",
            }
        )
    for raw_ev in memory.events:
        chronology.append(
            {
                "timestamp": raw_ev.get("date") or "",
                "kind": "reported_event",
                "actor": "user_reported",
                "channel": None,
                "summary": raw_ev.get("description", ""),
                "status": "user_reported",
                "grounding": "reported_by_user",
            }
        )
    for act in user_actions:
        chronology.append(
            {
                "timestamp": act.get("occurred_at") or act.get("updated_at"),
                "kind": "user_tracked_action",
                "actor": "user",
                "channel": None,
                "summary": f"{act['title']} ({act['status']})"
                + (f" — {act['notes']}" if act.get("notes") else ""),
                "status": act["status"],
                "grounding": "reported_by_user",
            }
        )
    chronology.sort(key=lambda item: str(item.get("timestamp") or ""))

    evidence_index = [
        {
            "attachment_id": a["id"],
            "filename": a["filename"],
            "mime_type": a["mime_type"],
            "size_bytes": a["size"],
            "extraction_status": a["extraction_status"],
            "consent_status": a.get("consent_status", "consented"),
            "uploaded_at": a["created_at"],
        }
        for a in attachments
    ]

    unresolved: list[str] = list(
        dict.fromkeys(
            list(memory.questions_for_legal_review)
            + list(memory.legal_issues_for_review)
            + list(memory.unknowns)
        )
    )
    for msg in assistant_msgs[-3:]:
        meta = msg.get("metadata") or {}
        for l_issue in meta.get("legal_issues") or []:
            if l_issue not in unresolved:
                unresolved.append(l_issue)
        for blk in meta.get("resolution_blocks") or []:
            if blk.get("block_type") in {"limitation", "question"} and blk.get("content"):
                if blk["content"] not in unresolved:
                    unresolved.append(blk["content"])

    published_sources: dict[str, dict[str, Any]] = {}
    structured_findings: list[dict[str, Any]] = []
    for msg in assistant_msgs[-5:]:
        meta = msg.get("metadata") or {}
        for src in meta.get("sources") or []:
            pid = src.get("passage_id") or src.get("source_id")
            if pid and pid not in published_sources:
                published_sources[pid] = {
                    "source_id": src.get("source_id"),
                    "passage_id": src.get("passage_id"),
                    "title": src.get("title"),
                    "locator": src.get("locator"),
                    "canonical_url": src.get("canonical_url"),
                    "verification_status": src.get("verification_status"),
                    "effective_date": src.get("effective_date"),
                    "limitations": src.get("limitations"),
                }
        for blk in meta.get("resolution_blocks") or []:
            if blk.get("block_type") in {"direct_answer", "recommended_route", "alternatives"}:
                structured_findings.append(
                    {
                        "message_id": msg["id"],
                        "block_type": blk["block_type"],
                        "title": blk["title"],
                        "content": blk["content"],
                        "grounding": blk["grounding"],
                        "source_ids": blk.get("source_ids", []),
                    }
                )

    prepared_drafts = [
        {
            "draft_id": d["id"],
            "title": d["title"],
            "version": d["version"],
            "status": d["status"],
            "case_version": d["case_version"],
            "content": d["content"],
            "updated_at": d["updated_at"],
        }
        for d in drafts
    ]

    return {
        "bundle_version": "escalation-bundle-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "conversation_id": conversation["id"],
        "case_title": conversation["title"],
        "language": conversation["language"],
        "domain": memory.domain,
        "case_version": memory.version,
        "escalation_recommended": bool(reasons),
        "escalation_reasons": reasons
        or ["User-requested legal review or representation readiness package."],
        "executive_summary": summary or "User-reported legal dispute workspace.",
        "chronology": chronology,
        "facts_partition": {
            "reported_and_consistent": consistent_facts,
            "uncertain_or_disputed": uncertain_facts,
            "contradictions": list(memory.contradictions),
        },
        "evidence_index": evidence_index,
        "unresolved_legal_questions": unresolved[:12],
        "generated_drafts": prepared_drafts,
        "source_backed_analysis": {
            "findings": structured_findings[-8:],
            "verified_sources": list(published_sources.values()),
            "contains_hidden_model_reasoning": False,
        },
        "submission_trail": submission_steps,
        "autonomy_notice": (
            "Nyay Saathi prepares analysis and drafts only. No filing, signature, payment, "
            "or legal representation has been performed on the user's behalf."
        ),
    }
