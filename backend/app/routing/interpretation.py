"""Side-effect-free interpretation. No database, retrieval, or case-write tools."""

import json
import re
from typing import Protocol

from langchain_openai import ChatOpenAI

from app.routing.contracts import RequestInterpretation, TaskIntent
from app.routing.segments import (
    PROMPT,
    SegmentInterpretation,
    resolve_interpretation,
    segment_message,
)
from app.services.model_calls import model_calls


class InterpretationError(ValueError):
    def __init__(self, code, task_ids=()):
        super().__init__(code)
        self.code, self.task_ids = code, list(task_ids)


LEGAL_DOMAINS = {"consumer", "employment", "tenancy", "criminal", "other_legal"}


def source_span_matches(source_text: str, message: str) -> bool:
    if source_text in message:
        return True
    norm_source = " ".join(source_text.split())
    norm_message = " ".join(message.split())
    if norm_source and norm_source.casefold() in norm_message.casefold():
        return True
    clauses = [
        c.strip() for c in re.split(r"(?:[.?!;\n]+|\.\.\.|…)", norm_source) if len(c.strip()) >= 6
    ]
    if clauses and all(c.casefold() in norm_message.casefold() for c in clauses):
        return True
    source_words = re.findall(r"\w+", norm_source.casefold())
    message_words = set(re.findall(r"\w+", norm_message.casefold()))
    if len(source_words) >= 4:
        overlap = sum(1 for w in source_words if w in message_words) / len(source_words)
        if overlap >= 0.75:
            return True
    return False


def _collapse_redundant_case_updates(tasks: list[TaskIntent], message: str) -> list[TaskIntent]:
    if not any(t.intent == "case_update" for t in tasks):
        return tasks
    actionable_intents = {"legal_options", "draft", "revision", "summary", "evidence"}
    domains_with_actionable = {
        t.domain for t in tasks if t.domain in LEGAL_DOMAINS and t.intent in actionable_intents
    }
    if not domains_with_actionable:
        return tasks
    kept: list[TaskIntent] = []
    updated_domains: set[str] = set()
    for t in tasks:
        if t.domain in domains_with_actionable and t.intent == "case_update":
            continue
        if (
            t.domain in domains_with_actionable
            and t.intent in actionable_intents
            and t.domain not in updated_domains
        ):
            has_case_update = any(
                other.domain == t.domain
                and (other.intent == "case_update" or other.requires_case_update)
                for other in tasks
            )
            updates = {"requires_case_update": t.requires_case_update or has_case_update}
            if len({other.domain for other in tasks if other.domain in LEGAL_DOMAINS}) == 1:
                updates["source_text"] = message.strip()
            t = t.model_copy(update=updates)
            updated_domains.add(t.domain)
        kept.append(t)
    if not kept:
        return tasks
    return [t.model_copy(update={"task_id": f"task-{idx + 1}"}) for idx, t in enumerate(kept)]


def derive_answer_requirements(message: str, tasks: list[TaskIntent], context: dict) -> dict:
    lower = message.casefold()
    facts = context.get("confirmed_and_reported_facts", {}) if isinstance(context, dict) else {}
    deliverables: list[str] = []
    elements: list[str] = []
    missing: list[str] = []

    intents = {t.intent for t in tasks}
    domains = {t.domain for t in tasks}
    is_booking = bool(re.search(r"\b(?:hotel|booking|check-?in|guest|property|stay)\b", lower))
    is_consumer = "consumer" in domains or bool(
        re.search(
            r"\b(?:refund|order|purchase|booking|check-?in|defective|not delivered|expired)\b",
            lower,
        )
    )
    has_discrepancy = bool(
        re.search(
            r"\b(?:refused|rejected|promised|wrong|expired|curdled|never received|marked delivered|discrepancy|allowed|permitted)\b",
            lower,
        )
    )

    if "legal_options" in intents or re.search(
        r"\b(?:who(?:m)? should i (?:approach|contact)|what should i do|next (?:practical )?step|options|escalat)\b",
        lower,
    ):
        deliverables.append("escalation_guidance")
    if "draft" in intents or re.search(
        r"\b(?:draft|write|complaint say|message asking|message challenging|email|letter)\b",
        lower,
    ):
        deliverables.append("complaint_draft")
    if "revision" in intents:
        deliverables.append("revised_draft")
    if "summary" in intents or re.search(r"\b(?:summary|brief for (?:a )?lawyer)\b", lower):
        deliverables.append("lawyer_brief" if "lawyer" in lower else "factual_summary")
    if "evidence" in intents or re.search(
        r"\bwhat (?:evidence|proof|documents?|records?)\b", lower
    ):
        deliverables.append("evidence_checklist")
    if domains & {"health", "animal_health"}:
        deliverables.append("safety_precaution")

    user_goal = None
    suggested_remedy = None
    if is_booking and is_consumer:
        user_goal = "recover_booking_payment"
        suggested_remedy = "request_full_refund"
    elif "consumer" in domains:
        user_goal = (
            "recover_order_payment"
            if re.search(
                r"\b(?:refund|return|not delivered|never received|expired|refused)\b", lower
            )
            else "resolve_consumer_dispute"
        )
        if re.search(
            r"\b(?:refund|return|not delivered|never received|defective|wrong|expired|curdled|refused)\b",
            lower,
        ):
            suggested_remedy = "request_full_refund"
    elif "employment" in domains:
        user_goal = "recover_unpaid_wages"
        suggested_remedy = "request_unpaid_salary_settlement"
    elif "tenancy" in domains:
        user_goal = "recover_security_deposit"
        suggested_remedy = "request_deposit_refund"
    elif "criminal" in domains:
        user_goal = "report_incident_and_preserve_evidence"
        suggested_remedy = "urgent_official_reporting_and_evidence_preservation"

    if is_consumer or (domains & LEGAL_DOMAINS):
        elements.append(
            "explain_factual_discrepancy" if has_discrepancy else "direct_factual_assessment"
        )
    if "escalation_guidance" in deliverables:
        elements.extend(["identify_initial_recipient", "provide_escalation_options"])
    if "complaint_draft" in deliverables:
        elements.append(
            "draft_refund_request"
            if suggested_remedy == "request_full_refund"
            else "prepare_requested_draft"
        )
    if (
        "evidence_checklist" in deliverables
        or "escalation_guidance" in deliverables
        or "complaint_draft" in deliverables
    ) and (is_consumer or (domains & LEGAL_DOMAINS)):
        elements.append("identify_essential_evidence")

    if is_booking and is_consumer:
        if not facts.get("booking_id") and not re.search(
            r"\bbooking\s*(?:id|no|ref|reference)\s*[:#]?\s*[a-z0-9-]{4,}", lower
        ):
            missing.append("booking_id")
        if not facts.get("property_name"):
            missing.append("property_name")
        if not facts.get("stay_dates") and not re.search(r"\b202\d\b", lower):
            missing.append("stay_dates")
        if not facts.get("amount") and not re.search(r"₹\s*\d+|\brs\.?\s*\d+", lower):
            missing.append("payment_amount")
    elif "consumer" in domains:
        if not facts.get("order_id") and not re.search(
            r"\border\s*(?:id|no|ref|reference)\s*[:#]?\s*[a-z0-9-]{4,}", lower
        ):
            missing.append("order_id")
        if not facts.get("amount") and not re.search(r"₹\s*\d+|\brs\.?\s*\d+", lower):
            missing.append("payment_amount")
        if not facts.get("order_date") and not re.search(r"\b202\d\b", lower):
            missing.append("order_date")
    elif "employment" in domains:
        if not facts.get("location"):
            missing.append("work_location")
        if not facts.get("employer_name"):
            missing.append("employer_legal_name")

    return {
        "requested_deliverables": list(dict.fromkeys(deliverables))[:8],
        "user_goal": user_goal,
        "suggested_remedy": suggested_remedy,
        "required_answer_elements": list(dict.fromkeys(elements))[:12],
        "missing_details": list(dict.fromkeys(missing))[:12],
    }


class Interpreter(Protocol):
    def interpret(self, message: str, context: dict) -> tuple[RequestInterpretation, dict, str]: ...


def conservative_interpretation(message, context):
    """Offline fallback, labelled as such. Relational cues precede industry words.

    This is not advertised as semantic model performance. Unclear inputs stay
    uncertain; no organization-name list determines the domain.
    """
    existing = bool(
        context.get("confirmed_and_reported_facts")
        or context.get("parties")
        or context.get("complaint_journey", {}).get("events")
    )
    prior = [
        m
        for m in context.get("recent_turns", [])
        if m.get("role") == "user" and m.get("content") != message
    ]
    previous = prior[-1]["content"] if prior else ""
    case_previous = bool(
        re.search(r"refund|complain|ordered|salary|landlord|defective|₹", previous, re.I)
    )
    parts = [
        s.strip()
        for s in re.split(
            r"(?<=[?;])\s+|\n+|\band also\b|(?<=[.])\s+(?=(?:what|who|whom|how|where|when|is|are|can|should|prepare|draft|write|suggest)\b)",
            message,
            flags=re.I,
        )
        if s.strip()
    ]
    tasks = []
    for part in parts[:8]:
        lower = part.casefold()
        domain, relationship = "general", None
        # Employment relations must take precedence over workplace/industry names.
        if re.search(
            r"salary|wages?|employer|employee|termination|appointment letter|unpaid.*काम|वेतन|तनख्वाह|naukri|tankhwa",
            lower,
        ):
            domain, relationship = "employment", "employee–employer"
        elif re.search(r"landlord|tenant|किराया|makaan malik", lower):
            domain, relationship = "tenancy", "tenant–landlord"
        elif re.search(r"arrest|\bfir\b|police|गिरफ्तार", lower):
            domain, relationship = "criminal", "person–law enforcement"
        elif re.search(
            r"(?:my |mera |मेरी |i .*?)(?:refund|order|purchase)|\brefund\b|ordered|booked a hotel|refused check-?in|check-?in.*(?:denied|refused)|denied entry|seller|defective|not delivered|wrong colo[u]?r|खरीद|रिफंड|mangaya|delivery.*nahi",
            lower,
        ):
            domain, relationship = "consumer", "buyer–seller or service provider"
        elif re.search(r"cow|veterinar|cucumber|गाय|pashu", lower):
            domain = "animal_health"
        elif re.search(r"safe to (?:drink|eat|consume)|smells bad|poison|बीमार|सुरक्षित", lower):
            domain = "health"
        if re.match(r"(?:what is|what does|define|tell me about)\b", lower) and not re.search(
            r"\bmy\b|\bi\b|₹", lower
        ):
            domain, relationship = "general", None
        continuation = bool(
            re.search(
                r"actually|shorter|polite|same amount|already sent|already complained|he said|what.*next|continue|hindi|हिंदी|असल में",
                lower,
            )
        )
        confirmation = bool(
            re.fullmatch(
                r"(?:yes(?:,? that['’]s right)?|correct|i confirm|हाँ|हां|सही है)[.!]?", lower.strip()
            )
        )
        if domain == "general" and (continuation or confirmation) and existing and case_previous:
            stored = context.get("case_domain", "consumer")
            domain = stored if stored in LEGAL_DOMAINS else "other_legal"
        uncertain_confirmation = confirmation and not (existing and case_previous)
        legal = domain in LEGAL_DOMAINS
        intent = "confirmation" if confirmation else "information"
        wants_draft = bool(
            re.search(
                r"draft|write|prepare.*(?:summary|complaint|brief)|factual brief|what should (?:my |the )?(?:complaint|email|letter|message) say|लिख|shorter|polite|hindi|हिंदी",
                lower,
            )
        )
        wants_options = bool(
            re.search(
                r"who(?:m)? should i (?:approach|contact)|what should i do|next (?:practical )?step|what (?:are )?my (?:options|rights)|complaint authority|appropriate .* authority",
                lower,
            )
        )
        wants_evidence = bool(re.search(r"evidence|proof|documents|सबूत", lower))
        if (
            domain == "general"
            and (wants_draft or wants_options or wants_evidence)
            and any(t.domain in LEGAL_DOMAINS for t in tasks)
        ):
            prev_legal = next(t for t in reversed(tasks) if t.domain in LEGAL_DOMAINS)
            domain, relationship = prev_legal.domain, prev_legal.relationship
            legal = True
        if wants_draft and wants_options and legal:
            intent = "legal_options"
        elif wants_evidence and wants_draft and legal:
            intent = "evidence"
        elif wants_draft:
            intent = (
                "revision"
                if continuation
                else "summary"
                if ("summary" in lower or "brief" in lower)
                else "draft"
            )
        elif wants_evidence:
            intent = "evidence"
        elif re.search(r"\b(?:search|look up)\b|\bcheck\b(?!-?\s*in\b|\s*out\b)|खोज", lower):
            intent = "search"
        elif legal:
            intent = (
                "legal_options"
                if re.search(r"\b(?:what|how|who|next|complaint|rights|kaise)\b|क्या", lower)
                else "case_update"
            )
        if uncertain_confirmation:
            intent = "clarify"
        link = (
            "uncertain"
            if uncertain_confirmation
            else "existing"
            if legal and existing
            else "new"
            if legal
            else "unrelated"
        )
        stored_domain = context.get("case_domain")
        if (
            legal
            and existing
            and stored_domain
            not in {None, "unknown", domain, "unpaid_salary" if domain == "employment" else domain}
        ):
            link = "new"
        risk = (
            "urgent"
            if re.search(
                r"cannot breathe|can't breathe|unconscious|hearing tomorrow|summons|threatened to kill|choking|सांस नहीं",
                lower,
            )
            else "sensitive"
            if domain in {"health", "animal_health", "criminal"}
            else "ordinary"
        )
        tasks.append(
            TaskIntent(
                task_id=f"task-{len(tasks) + 1}",
                source_text=part,
                intent=intent,
                domain=domain,
                relationship=relationship,
                entities=[],
                case_link=link,
                requires_research=bool(
                    intent in {"search", "legal_options"}
                    or domain in {"health", "animal_health"}
                    or re.search(r"ipo|latest|current|today|released", lower)
                ),
                requires_case_update=legal and not uncertain_confirmation,
                risk_level=risk,
                uncertainty=[
                    "Offline interpretation; contextual model classification has not run."
                ],
                public_query=None,
            )
        )
        if wants_draft and (wants_options or wants_evidence) and legal and len(tasks) < 8:
            tasks.append(
                TaskIntent(
                    task_id=f"task-{len(tasks) + 1}",
                    source_text=part,
                    intent="summary" if ("summary" in lower or "brief" in lower) else "draft",
                    domain=domain,
                    relationship=relationship,
                    entities=[],
                    case_link=link,
                    requires_research=False,
                    requires_case_update=False,
                    risk_level=risk,
                    uncertainty=[
                        "Offline interpretation; contextual model classification has not run."
                    ],
                    public_query=None,
                )
            )
        # Mixed safety and complaint stories need independent treatment.
        if (
            legal
            and re.search(r"safe to (?:drink|eat|consume)|smells bad|poison", lower)
            and len(tasks) < 8
        ):
            tasks.append(
                TaskIntent(
                    task_id=f"task-{len(tasks) + 1}",
                    source_text=part,
                    intent="information",
                    domain="health",
                    relationship=None,
                    entities=[],
                    case_link="unrelated",
                    requires_research=True,
                    requires_case_update=False,
                    risk_level="sensitive",
                    uncertainty=["Safety assessment requires appropriate sources."],
                    public_query=None,
                )
            )
    tasks = _collapse_redundant_case_updates(tasks, message)
    if not tasks:
        tasks = [
            TaskIntent(
                task_id="task-1",
                source_text=message or " ",
                intent="clarify",
                domain="unknown",
                relationship=None,
                entities=[],
                case_link="uncertain",
                requires_research=False,
                requires_case_update=False,
                risk_level="ordinary",
                uncertainty=["No interpretable request"],
                public_query=None,
            )
        ]
    links = {t.case_link for t in tasks}
    relevance = "mixed" if len(links) > 1 else next(iter(links))
    requirements = derive_answer_requirements(message, tasks, context)
    return RequestInterpretation(
        tasks=tasks,
        case_relevance=relevance,
        clarification_needed=any(t.case_link == "uncertain" for t in tasks),
        **requirements,
    )


class ContextualInterpreter:
    def __init__(self, settings, model_factory=ChatOpenAI):
        self.settings = settings
        self.model_factory = model_factory
        self.prompt = PROMPT.read_text()

    def interpret(self, message, context):
        if not self.settings.ai_configured:
            return conservative_interpretation(message, context), {}, "offline_fallback"
        result = model_calls.structured(
            self.model_factory,
            SegmentInterpretation,
            [
                ("system", self.prompt),
                (
                    "user",
                    json.dumps(
                        {
                            "segments": segment_message(message),
                            "context": {
                                k: context.get(k)
                                for k in (
                                    "case_domain",
                                    "case_confirmation_eligible",
                                    "pending_question_or_stage",
                                    "rolling_summary",
                                    "recent_turns",
                                    "contradictions",
                                    "runtime",
                                )
                            },
                        },
                        ensure_ascii=False,
                    ),
                ),
            ],
            self.settings,
            "interpretation",
        )
        value = result.get("parsed")
        data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        if data is None:
            data = json.loads(getattr(result.get("raw"), "content", ""))
        if data.get("schema_version") != "request-v1":
            with model_calls.validation("interpretation"):
                resolved = resolve_interpretation(data, message)
            return (
                resolved,
                getattr(result.get("raw"), "usage_metadata", {}) or {},
                "model_partial" if resolved.invalid_tasks else "model",
            )
        parsed = RequestInterpretation.model_validate(result.get("parsed"))
        mismatches = [
            task.task_id
            for task in parsed.tasks
            if not source_span_matches(task.source_text, message)
        ]
        if mismatches:
            raise InterpretationError("source_span_mismatch", mismatches)
        collapsed_tasks = _collapse_redundant_case_updates(list(parsed.tasks), message)
        derived = derive_answer_requirements(message, collapsed_tasks, context)
        updates = {
            key: getattr(parsed, key) or derived[key]
            for key in (
                "requested_deliverables",
                "user_goal",
                "suggested_remedy",
                "required_answer_elements",
                "missing_details",
            )
            if not getattr(parsed, key) and derived.get(key)
        }
        if collapsed_tasks != list(parsed.tasks):
            updates["tasks"] = collapsed_tasks
            links = {t.case_link for t in collapsed_tasks}
            updates["case_relevance"] = "mixed" if len(links) > 1 else next(iter(links))
        if updates:
            parsed = parsed.model_copy(update=updates)
        return parsed, getattr(result.get("raw"), "usage_metadata", {}) or {}, "model"


class OfflineInterpreter:
    """Explicit test/offline adapter; never presented as model interpretation."""

    def interpret(self, message, context):
        return conservative_interpretation(message, context), {}, "offline_fixture"
