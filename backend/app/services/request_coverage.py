"""Detect and account for the user's latest explicit requests.

This module is intentionally deterministic. The model may refine the wording, but it
cannot silently discard a separately requested output.
"""

import re

from app.schemas.models import ExplicitRequest, RequestCoverageItem, ResponseEnvelope

REQUEST_PATTERNS: list[tuple[str, tuple[str, ...], bool]] = [
    (
        "evidence_checklist",
        (
            r"\bwhat (?:evidence|proof|documents?)\b",
            r"\b(?:evidence|documents?) (?:should|do) i (?:collect|keep|need)\b",
            r"\bprepare (?:an? )?evidence checklist\b",
            r"(?:क्या|कौन से) (?:सबूत|दस्तावेज)",
        ),
        False,
    ),
    (
        "factual_summary",
        (
            r"\b(?:prepare|make|write|give|create) (?:me )?(?:an? )?(?:factual )?(?:complaint |case )?summary\b",
            r"\bsummari[sz]e\b",
            r"\bbrief (?:for|to) (?:a |my )?lawyer\b",
            r"(?:सारांश|संक्षेप).*(?:बना|लिख|तैयार)",
        ),
        False,
    ),
    (
        "revision",
        (
            r"\bmake it (?:shorter|more polite|firmer|simpler|clearer)\b",
            r"\b(?:revise|edit|shorten|rewrite) (?:it|that|the draft)\b",
            r"\buse the same (?:amount|date|details?)\b",
            r"(?:छोटा|संक्षिप्त|विनम्र).*(?:कर|बना)",
        ),
        False,
    ),
    (
        "translation",
        (
            r"\b(?:explain|say|write|translate) (?:it|that|this)?\s*(?:in|into) hindi\b",
            r"\b(?:explain|say|write|translate) (?:it|that|this)?\s*(?:in|into) hinglish\b",
            r"(?:हिंदी|हिंग्लिश) में (?:समझा|लिख|बत)",
        ),
        False,
    ),
    (
        "practice",
        (
            r"\bpracti[cs]e\b",
            r"\brole[ -]?play\b",
            r"\bwhat (?:might|will) (?:the seller|they|the other side) say\b",
        ),
        False,
    ),
    (
        "draft",
        (
            r"\b(?:draft|write|prepare|create) (?:me )?(?:an? )?(?:complaint|email|letter|notice|reply|grievance)\b",
            r"\bcomplaint (?:email|letter|draft)\b",
            r"(?:शिकायत|ईमेल|पत्र|जवाब).*(?:लिख|तैयार|बना)",
        ),
        False,
    ),
    (
        "options",
        (
            r"\bwhat should i do(?: next)?\b",
            r"\bwhat (?:are )?my (?:options|rights)\b",
            r"\bwhat can i do\b",
            r"\bwhich (?:route|forum|authority)\b",
            r"(?:अब|आगे) क्या करूँ|मेरे (?:विकल्प|अधिकार)",
        ),
        True,
    ),
    (
        "explanation",
        (
            r"\b(?:explain|tell me|what does|how does|can you help)\b",
            r"\bin what cases can you help\b",
            r"(?:समझा|बताइए|बताओ)",
        ),
        False,
    ),
]


def detect_explicit_requests(text: str) -> list[ExplicitRequest]:
    """Return stable, ordered request items for the latest message only."""
    found: list[ExplicitRequest] = []
    lower = text.casefold()
    for kind, patterns, legal in REQUEST_PATTERNS:
        if any(re.search(pattern, lower, re.I) for pattern in patterns):
            # A factual complaint summary is a summary, not a request for complaint prose.
            if kind == "draft" and any(item.kind == "factual_summary" for item in found):
                if not re.search(r"\b(?:draft|letter|email|notice|grievance)\b", lower):
                    continue
            found.append(
                ExplicitRequest(
                    request_id=f"request-{len(found) + 1}",
                    kind=kind,
                    request_text=_request_label(kind, text),
                    requires_legal_retrieval=legal,
                )
            )
    if not found:
        found.append(
            ExplicitRequest(
                request_id="request-1",
                kind="case_update",
                request_text=text.strip()[:500],
                requires_legal_retrieval=False,
            )
        )
    return found


def _request_label(kind: str, text: str) -> str:
    labels = {
        "evidence_checklist": "Explain what evidence to collect",
        "factual_summary": "Prepare a factual complaint summary",
        "draft": "Prepare the requested document",
        "revision": "Revise the previous answer or draft as requested",
        "translation": "Provide the requested language version",
        "options": "Explain practical next steps or options",
        "practice": "Practise the other side's response and a truthful reply",
        "explanation": "Answer the user's question",
    }
    return labels.get(kind, text.strip()[:500])


def merge_requests(
    deterministic: list[ExplicitRequest], model_items: list[ExplicitRequest]
) -> list[ExplicitRequest]:
    """Keep deterministic coverage and add genuinely new model-detected request kinds."""
    merged = list(deterministic)
    known = {item.kind for item in merged}
    for item in model_items:
        if item.kind not in known and item.kind != "case_update":
            merged.append(item.model_copy(update={"request_id": f"request-{len(merged) + 1}"}))
            known.add(item.kind)
    return merged


def finalise_response(
    envelope: ResponseEnvelope, requests: list[ExplicitRequest]
) -> tuple[str, list[RequestCoverageItem], list[str]]:
    """Render user language only; the review model, not this renderer, judges coverage."""
    del requests
    coverage = list(envelope.request_coverage)
    message = envelope.message_markdown.strip()
    # One focused question is the default. The model may propose two, but keeping the
    # first avoids turning an ordinary reply into an intake form.
    questions = [q.strip() for q in envelope.follow_up_questions if q.strip()][:1]
    if questions:
        question = questions[0]
        if not question.endswith("?"):
            question += "?"
        if question.casefold() not in message.casefold():
            message += f"\n\n{question}"
    return message, coverage, questions


INTERNAL_RENDER_TERMS = (
    "confirmed_and_reported_facts",
    "rewritten_query",
    "request_coverage",
    "verification_findings",
    "graph_state",
    "research_plan",
    "supporting_passage_ids",
    "fetched_pending_review",
    "resolution_plan",
    "document_markdown",
    "required_fields",
)


def contains_internal_rendering(text: str) -> bool:
    lower = text.casefold()
    return any(term in lower for term in INTERNAL_RENDER_TERMS)
