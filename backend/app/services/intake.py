import re
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import Settings
from app.routing.interpretation import conservative_interpretation
from app.schemas.models import IntakeExtraction
from app.services.model_calls import model_calls
from app.services.request_coverage import detect_explicit_requests
from app.services.review_policy import ReviewPolicy

CONSUMER_TERMS = {
    "refund": "refund_not_received",
    "return": "refund_refused",
    "defective": "defective_goods",
    "broken": "defective_goods",
    "not delivered": "non_delivery",
    "non-delivery": "non_delivery",
    "seller": "consumer",
    "order": "consumer",
    "product": "consumer",
}
UNSUPPORTED_TERMS = {
    "landlord": "landlord_deposit",
    "deposit": "landlord_deposit",
    "salary": "unpaid_salary",
    "employer": "employment",
    "fir": "criminal",
    "police": "criminal",
    "arrest": "criminal",
}
URGENT_TERMS = {
    "summons": "A court summons or hearing notice may require prompt professional review.",
    "hearing tomorrow": "A possible imminent hearing deadline requires prompt professional review.",
    "threatened to kill": "A threat to immediate safety requires emergency help, not only legal information.",
    "arrest": "A criminal matter and possible loss of liberty require prompt qualified legal help.",
}


def is_explicit_correction(text: str) -> bool:
    return bool(
        re.search(
            r"\b(actually|correction|i meant|not .{0,20}but|गलत|असल में|मेरा मतलब)\b",
            text.casefold(),
        )
    )


def deterministic_extract(text: str) -> IntakeExtraction:
    lower = text.casefold()
    domain = "unknown"
    issue = None
    interpretation = conservative_interpretation(text, {})
    legal = next(
        (
            task
            for task in interpretation.tasks
            if task.domain not in {"general", "health", "animal_health", "unknown"}
        ),
        None,
    )
    if legal:
        domain = {"tenancy": "landlord_deposit", "other_legal": "other_unsupported"}.get(
            legal.domain, legal.domain
        )
        if domain == "employment" and "salary" in lower:
            domain = "unpaid_salary"
    if domain == "consumer":
        issue = next((found for term, found in CONSUMER_TERMS.items() if term in lower), "consumer")
    proposed: list[dict[str, str]] = []
    for match in re.finditer(r"(?:₹|rs\.?\s*|inr\s*)([\d,]+(?:\.\d{1,2})?)", text, re.I):
        proposed.append(
            {"key": "amount", "value": match.group(1).replace(",", ""), "status": "user_allegation"}
        )
    date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", text)
    if date_match:
        proposed.append(
            {"key": "reported_date", "value": date_match.group(1), "status": "user_allegation"}
        )
    if issue:
        proposed.append({"key": "issue_type", "value": issue, "status": "user_allegation"})
    correction = is_explicit_correction(text)
    completed = []
    if re.search(
        r"\b(i (?:already )?(?:sent|emailed|called|complained)|मैंने .*(?:भेज|कॉल|शिकायत))", lower
    ):
        completed.append(text[:500])
    urgent = next((reason for term, reason in URGENT_TERMS.items() if term in lower), None)
    needs_legal = bool(
        re.search(
            r"\b(what should i do|next|rights?|legal|law|complaint|section|option|क्या करूँ|अधिकार)\b",
            lower,
        )
    )
    intent = (
        "draft"
        if re.search(
            r"\b(draft|write|email|notice|complaint letter|revise|polite|shorter|same amount|make it|लिख)\b",
            lower,
        )
        else "options"
        if needs_legal
        else "intake"
    )
    explicit_requests = detect_explicit_requests(text)
    if any(item.kind in {"draft", "revision", "factual_summary"} for item in explicit_requests):
        intent = "draft"
    elif any(item.kind == "practice" for item in explicit_requests):
        intent = "practice"
    elif any(item.kind == "options" for item in explicit_requests):
        intent = "options"
    contradictions = (
        ["The user explicitly indicated a correction; compare proposed values with stored facts."]
        if correction
        else []
    )
    return IntakeExtraction(
        domain=domain,
        proposed_facts=proposed,
        parties=[],
        locations=[],
        events=[],
        requested_remedy="refund"
        if re.search(r"\b(?:want|need|seeking|request(?:ing)?) (?:a |the )?refund\b", lower)
        else None,
        completed_actions=completed,
        responses_received=[],
        correspondence=[],
        contradictions=contradictions,
        urgent_reason=urgent,
        needs_legal_retrieval=needs_legal and domain == "consumer",
        intent=intent,
        questions=[],
        explicit_requests=explicit_requests,
    )


def is_explicit_confirmation(text: str) -> bool:
    """Recognise direct fact confirmation without accepting a casual yes in prose."""
    normalised = text.casefold().replace("’", "'").replace("‘", "'")
    normalised = re.sub(r"[^\w\u0900-\u097f']+", " ", normalised).strip()
    return bool(
        re.fullmatch(
            r"(?:yes|yes correct|yes that(?:'s| is) right|that(?:'s| is) right|that is correct|those facts are correct|looks right|i confirm|confirmed|correct|हाँ|हां|जी हाँ|जी हां|सही है|यह सही है|मैं पुष्टि करता हूँ|मैं पुष्टि करती हूँ)",
            normalised,
        )
    )


class IntakeService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.prompt = (Path(__file__).parents[1] / "prompts" / "v1" / "intake.md").read_text()

    def extract(
        self,
        text: str,
        context: dict[str, Any],
        shared_guidance: dict[str, Any] | None = None,
    ) -> tuple[IntakeExtraction, dict[str, int]]:
        baseline = deterministic_extract(text)
        if not self.settings.ai_configured or ReviewPolicy.simple_intake(text, context):
            return baseline, {}
        result = model_calls.structured(
            ChatOpenAI,
            IntakeExtraction,
            [
                ("system", self.prompt),
                (
                    "user",
                    f"Context:\n{context}\n\n"
                    "APPLICATION PLAYBOOK (guidance, not legal authority):\n"
                    f"{shared_guidance or {}}\n\nCurrent message:\n{text}",
                ),
            ],
            self.settings,
            "extraction",
        )
        parsed = result.get("parsed") or baseline
        raw = result.get("raw")
        usage = getattr(raw, "usage_metadata", None) or {}
        return parsed, {k: int(v) for k, v in usage.items() if isinstance(v, int)}
