"""Structured resolution response blocks with grounding provenance, clickable sources, and Markdown."""

from __future__ import annotations

import re
from typing import Any

from app.agent.contracts import (
    AgentAnswer,
    AnswerClaim,
    BlockSourceRef,
    BlockType,
    GroundingLabel,
    ResolutionBlock,
)
from app.agent.safety import is_physical_liberty_category
from app.agent.verification import template_text
from app.answers.evidence import citation_marker

URGENT_BLOCK_ORDER: tuple[BlockType, ...] = (
    "direct_answer",
    "immediate_actions",
    "recommended_route",
    "alternatives",
    "evidence_checklist",
    "document",
    "question",
    "limitation",
)

NON_URGENT_BLOCK_ORDER: tuple[BlockType, ...] = (
    "direct_answer",
    "recommended_route",
    "immediate_actions",
    "alternatives",
    "evidence_checklist",
    "document",
    "question",
    "limitation",
)

BLOCK_ORDER: tuple[BlockType, ...] = URGENT_BLOCK_ORDER + ("human_handoff",)

BLOCK_TITLES: dict[BlockType, dict[str, str]] = {
    "direct_answer": {
        "en": "In short",
        "hi": "संक्षेप में",
        "hinglish": "Short mein",
    },
    "immediate_actions": {
        "en": "What you can do today",
        "hi": "आज आप क्या कर सकते हैं",
        "hinglish": "Aaj aap kya kar sakte hain",
    },
    "recommended_route": {
        "en": "What I'd suggest",
        "hi": "मेरी सलाह",
        "hinglish": "Meri salah",
    },
    "alternatives": {
        "en": "If that doesn't work",
        "hi": "अगर इससे बात न बने",
        "hinglish": "Agar isse baat na bane",
    },
    "evidence_checklist": {
        "en": "Keep these ready",
        "hi": "ये चीज़ें तैयार रखें",
        "hinglish": "Ye cheezein ready rakhein",
    },
    "document": {
        "en": "Here's a draft you can use",
        "hi": "आपके लिए एक मसौदा",
        "hinglish": "Aapke liye ek draft",
    },
    "question": {
        "en": "One thing that would help me",
        "hi": "एक बात बताइए",
        "hinglish": "Ek baat bataiye",
    },
    "limitation": {
        "en": "What I can't confirm yet",
        "hi": "जो अभी पक्का नहीं है",
        "hinglish": "Jo abhi pakka nahi hai",
    },
    "human_handoff": {
        "en": "When a lawyer would help",
        "hi": "वकील की मदद कब लें",
        "hinglish": "Vakil ki madad kab lein",
    },
}

# Model-written "[2]"-style numbers would read as citations the runtime never assigned.
MODEL_CITATION_NUMBER_RE = re.compile(r"[ \t]?\[\d{1,2}\](?![(\[:])")

BLANKET_DISCLAIMER_RE = re.compile(
    r"(?:i am not a lawyer|not legal advice|i (?:could not|have not) verif\w+ (?:the )?(?:current )?(?:legal|statutory) (?:details|procedure)|the incident and your state or city are not known)",
    re.I,
)


def infer_block_type(claim: AnswerClaim) -> BlockType:
    if claim.block_type is not None:
        return claim.block_type
    if claim.in_document or claim.kind == "document":
        return "document"
    if claim.kind == "question":
        return "question"
    if claim.kind == "limitation" or claim.template_id in {"limited_research", "configuration"}:
        return "limitation"
    if claim.template_id == "preserve_records":
        return "evidence_checklist"
    if claim.template_id == "cyber_fraud_emergency_steps":
        return "immediate_actions"
    if claim.kind == "procedure":
        return "recommended_route"
    if claim.kind in {"practical", "safety"}:
        return "immediate_actions"
    return "direct_answer"


def claim_uses_legal_source(claim: AnswerClaim, btype: BlockType) -> bool:
    """Only attach legal/official source citations to legal/procedural claims—never practical checklists."""
    if btype in {"evidence_checklist", "document", "question"}:
        return False
    if claim.kind in {"practical", "factual", "quote"} and claim.grounding != "verified_legal_source":
        return False
    return claim.kind in {"legal", "procedure", "safety"} or claim.grounding == "verified_legal_source"


def resolve_grounding(claim: AnswerClaim, registry, btype: BlockType | None = None) -> GroundingLabel:
    effective_btype = btype or infer_block_type(claim)
    if effective_btype == "evidence_checklist":
        return "practical_precaution"
    public_ids = registry.public_ids()
    has_public = any(eid in public_ids for eid in claim.evidence_ids)
    if claim.grounding == "verified_legal_source":
        if claim.kind == "practical" and effective_btype in {"evidence_checklist", "document"}:
            return "practical_precaution"
        return "verified_legal_source" if has_public else "requires_confirmation"
    if claim.grounding is not None:
        return claim.grounding
    if has_public and claim_uses_legal_source(claim, effective_btype):
        return "verified_legal_source"
    if claim.kind in {"quote", "factual"} and claim.evidence_ids:
        return "reported_by_user"
    if claim.kind in {"question", "limitation"} or claim.template_id in {
        "limited_research",
        "configuration",
    }:
        return "requires_confirmation"
    return "practical_precaution"


def _dominant_grounding(labels: list[GroundingLabel]) -> GroundingLabel:
    if not labels:
        return "practical_precaution"
    if "verified_legal_source" in labels:
        return "verified_legal_source"
    if "requires_confirmation" in labels and set(labels) == {"requires_confirmation"}:
        return "requires_confirmation"
    if "reported_by_user" in labels and "practical_precaution" not in labels:
        return "reported_by_user"
    if "practical_precaution" in labels:
        return "practical_precaution"
    return labels[0]


def format_claim_text(claim: AnswerClaim, language: str) -> str:
    if claim.kind == "template":
        return template_text(claim.template_id, language)
    if claim.kind == "quote":
        return f"You report: “{claim.text}”"
    if claim.in_document:
        return claim.text
    return MODEL_CITATION_NUMBER_RE.sub("", claim.text)


def append_citation_markers(text: str, numbers: list[int]) -> str:
    """Attach "[1](#cite-1)" markers after the claim; tables, headings and code keep their own line."""
    if not numbers:
        return text
    markers = "".join(citation_marker(n) for n in numbers)
    body = text.rstrip()
    last_line = body.splitlines()[-1].lstrip() if body else ""
    separator = "\n\n" if last_line.startswith(("|", "#", "```")) else " "
    return body + separator + markers


def _physical_liberty_handoff_needed(answer: AgentAnswer, state: dict[str, Any]) -> bool:
    """Attach liberty/coercion lawyer handoff ONLY on physical-danger / detention / DV turns."""
    safety_msgs = state.get("safety_messages") or []
    if any(is_physical_liberty_category(m.get("category")) for m in safety_msgs):
        return True
    if state.get("urgent_continuation"):
        return True
    risk_types = set(answer.risk_types or [])
    if answer.action_plan and answer.action_plan.risk_types:
        risk_types |= set(answer.action_plan.risk_types)
    if risk_types & {"physical_danger", "domestic_violence"}:
        return True
    if risk_types and not (risk_types & {"physical_danger", "domestic_violence"}):
        # Explicit non-physical risks (e.g., financial_fraud, digital_compromise, self_harm)
        return False
    if safety_msgs and all(
        m.get("category") in {"financial_cyber_fraud", "self_harm", "medical_emergency"}
        for m in safety_msgs
    ):
        return False
    return answer.risk == "urgent"


LIBERTY_RE = re.compile(
    r"\b(?:jail|arrest\w*|custody|detain\w*|giraftar\w*|hirasat|lock-?up|bail|jamanat)\b"
    r"|जेल|गिरफ्तार|हिरासत|जमानत",
    re.I,
)


def handoff_template_id(answer: AgentAnswer, state: dict[str, Any]) -> str | None:
    """Referral the runtime guarantees on crisis, safety and liberty turns, whatever the model wrote."""
    categories = {m.get("category") for m in state.get("safety_messages") or []}
    risks = set(answer.risk_types or [])
    if answer.action_plan:
        risks |= set(answer.action_plan.risk_types)
    if "self_harm" in categories | risks:
        return "handoff_crisis"
    if "domestic_violence" in categories | risks:
        return "handoff_safety"
    if _physical_liberty_handoff_needed(answer, state):
        return "handoff_liberty"
    context = state.get("context") or {}
    conversation = " ".join(
        [state.get("current_message", "")]
        + [t.get("content", "") for t in context.get("recent_turns", []) if t.get("role") == "user"]
    )
    delivered = (context.get("prior_assistant_coverage") or {}).get("delivered_block_types") or []
    # Custody mentioned without an emergency: refer once per conversation, not on every turn.
    if LIBERTY_RE.search(conversation) and "human_handoff" not in delivered:
        return "handoff_liberty"
    return None


def effective_block_order(answer: AgentAnswer, state: dict[str, Any]) -> tuple[BlockType, ...]:
    """Place immediate_actions first on urgent safety turns; place recommended_route first on non-urgent disputes."""
    is_urgent = (
        answer.risk == "urgent"
        or bool(state.get("safety_messages"))
        or bool(state.get("urgent_continuation"))
        or _physical_liberty_handoff_needed(answer, state)
    )
    return URGENT_BLOCK_ORDER if is_urgent else NON_URGENT_BLOCK_ORDER


def assemble_resolution_blocks(
    answer: AgentAnswer,
    accepted: dict[str, str],
    registry,
    state: dict[str, Any],
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ordered, risk-calibrated resolution blocks with clean provenance and clickable sources."""
    language = state.get("language", "en")
    lang_key = language if language in {"en", "hi", "hinglish"} else "en"
    public_ids = registry.public_ids()
    order = effective_block_order(answer, state)

    doc_tasks_ok = {doc["task_id"]: doc for doc in documents}
    grouped: dict[
        BlockType, list[tuple[AnswerClaim, str, GroundingLabel, list[str], list[BlockSourceRef]]]
    ] = {b: [] for b in BLOCK_ORDER}

    for claim in answer.claims:
        if claim.claim_id not in accepted:
            continue
        btype = infer_block_type(claim)
        if claim.in_document and claim.task_id not in doc_tasks_ok:
            continue
        rendered = format_claim_text(claim, lang_key)
        if not rendered.strip():
            continue

        attach_sources = claim_uses_legal_source(claim, btype)
        src_ids: list[str] = []
        src_refs: list[BlockSourceRef] = []
        if attach_sources:
            for eid in claim.evidence_ids:
                if eid in public_ids:
                    entry = registry.entries[eid]
                    sid = entry.get("source_id") or eid
                    src_ids.append(sid)
                    url = entry.get("canonical_url") or ""
                    if url:
                        src_refs.append(
                            BlockSourceRef(
                                source_id=sid,
                                title=entry.get("title") or sid,
                                locator=entry.get("locator") or "",
                                canonical_url=url,
                            )
                        )
        grounding = resolve_grounding(claim, registry, btype)
        grouped[btype].append((claim, rendered, grounding, src_ids, src_refs))

    substantive_types = {
        "direct_answer",
        "immediate_actions",
        "recommended_route",
        "alternatives",
        "document",
    }
    has_substantive_help = any(bool(grouped[bt]) for bt in substantive_types) or any(
        e[0].kind != "template" for e in grouped["evidence_checklist"]
    )

    blocks: list[dict[str, Any]] = []
    # The lawyer / legal-aid referral always closes the answer, whatever the ordering above.
    for btype in (*order, "human_handoff"):
        entries = grouped[btype]
        if not entries:
            continue

        if btype == "question":
            entries = entries[:1]

        if btype == "limitation" and has_substantive_help:
            entries = [e for e in entries if not BLANKET_DISCLAIMER_RE.search(e[1])]
            if not entries:
                continue

        claim_ids = [e[0].claim_id for e in entries]
        source_ids = list(dict.fromkeys(sid for e in entries for sid in e[3]))
        seen_src_keys: set[tuple[str, str]] = set()
        dedup_sources: list[BlockSourceRef] = []
        for e in entries:
            for ref in e[4]:
                key = (ref.source_id, ref.locator)
                if key not in seen_src_keys:
                    seen_src_keys.add(key)
                    dedup_sources.append(ref)

        grounding = _dominant_grounding([e[2] for e in entries])
        texts = [e[1] for e in entries]

        if btype == "document" and documents:
            doc = documents[0]
            block = ResolutionBlock(
                block_id=f"block-{btype}",
                block_type=btype,
                title=doc["title"] or BLOCK_TITLES[btype][lang_key],
                content=doc["content"],
                items=[],
                claim_ids=claim_ids,
                source_ids=source_ids,
                sources=dedup_sources,
                grounding=grounding,
                document_title=doc["title"],
            )
        elif btype in {"immediate_actions", "alternatives", "evidence_checklist"}:
            items: list[str] = []
            for t in texts:
                split_lines = [
                    re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip()
                    for ln in t.splitlines()
                    if ln.strip() and not ln.strip().startswith("[Source:")
                ]
                if len(split_lines) > 1:
                    items.extend(split_lines)
                else:
                    items.append(t)
            block = ResolutionBlock(
                block_id=f"block-{btype}",
                block_type=btype,
                title=BLOCK_TITLES[btype][lang_key],
                items=items,
                content="\n\n".join(texts),
                claim_ids=claim_ids,
                source_ids=source_ids,
                sources=dedup_sources,
                grounding=grounding,
            )
        else:
            block = ResolutionBlock(
                block_id=f"block-{btype}",
                block_type=btype,
                title=BLOCK_TITLES[btype][lang_key],
                content="\n\n".join(texts),
                items=[],
                claim_ids=claim_ids,
                source_ids=source_ids,
                sources=dedup_sources,
                grounding=grounding,
            )
        blocks.append(block.model_dump(mode="json"))

    return blocks
