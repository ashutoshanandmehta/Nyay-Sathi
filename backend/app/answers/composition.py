"""Only verified text reaches the user. Composition introduces no generated assertions."""

LABELS = {
    "draft": "Complaint you can send",
    "revision": "Revised draft",
    "summary": "Factual summary",
    "evidence": "Evidence to prepare",
    "legal_options": "Who to contact",
    "information": "Assessment",
    "search": "Research",
    "case_update": "Direct assessment",
}

INTENT_ORDER = {
    "case_update": 1,
    "information": 2,
    "search": 2,
    "conversation": 2,
    "confirmation": 2,
    "legal_options": 3,
    "draft": 4,
    "revision": 4,
    "summary": 4,
    "practice": 4,
    "evidence": 5,
    "clarify": 6,
}


def _task_priority(task, index: int) -> tuple[int, int, int]:
    urgent = 0 if (task.risk_level == "urgent" or task.domain in {"health", "animal_health"}) else 1
    return (urgent, INTENT_ORDER.get(task.intent, 3), index)


class VerifiedComposer:
    def compose(self, units, registry, interpretation, language="en"):
        hindi = language == "hi"
        hinglish = language == "hinglish"
        task_map = {t.task_id: t for t in interpretation.tasks}
        order = {t.task_id: _task_priority(t, i) for i, t in enumerate(interpretation.tasks)}
        units = sorted(units, key=lambda u: order[u.task_id])
        visible_units = [
            u
            for u in units
            if not (task_map[u.task_id].intent == "case_update" and not u.claims and len(units) > 1)
        ]
        if not visible_units:
            visible_units = units
        pieces, documents, used = [], [], set()
        before_sending = []
        v2 = interpretation.schema_version == "request-v2"
        deferred_questions: list[str] = []
        question_rendered = False
        for idx, unit in enumerate(visible_units):
            task = task_map[unit.task_id]
            if unit.claims:
                content = []
                non_questions = [c for c in unit.claims if c.kind != "question"]
                questions = [c for c in unit.claims if c.kind == "question"]
                claims_to_render = non_questions if non_questions else questions[:1]
                if non_questions and questions:
                    for q in questions:
                        if q.text not in deferred_questions:
                            deferred_questions.append(q.text)
                elif not non_questions and questions:
                    question_rendered = True
                for claim in claims_to_render:
                    if (
                        v2
                        and task.intent in {"draft", "revision"}
                        and claim.kind == "preparation"
                        and "before sending" in claim.text[:40].casefold()
                    ):
                        before_sending.append(claim.text)
                        continue
                    content.append(claim.text)
                    if claim.kind != "limitation":
                        citation = registry.citations(claim.evidence_ids)
                        if citation:
                            content.append(citation)
                        used.update(set(claim.evidence_ids) & registry.public_ids())
                existing_limitations = {
                    c.text.strip() for c in claims_to_render if c.kind == "limitation"
                }
                if not existing_limitations and not v2:
                    for explanation in getattr(unit, "unresolved_explanations", [])[:1]:
                        content.append(explanation)
                        existing_limitations.add(explanation)
                text = "\n\n".join(content)
                if unit.document:
                    documents.append(
                        {
                            "task_id": unit.task_id,
                            "unit_id": unit.unit_id,
                            "title": "शिकायत का मसौदा"
                            if hindi
                            else "Factual summary"
                            if task.intent == "summary"
                            else "Prepared correspondence",
                            "content": unit.document,
                        }
                    )
            else:
                explanations = getattr(unit, "unresolved_explanations", [])
                if explanations and not hindi and not hinglish and not v2:
                    text = " ".join(explanations)
                else:
                    # Failure language depends on the task, not the entire case.
                    text = (
                        "उपलब्ध जानकारी से इस हिस्से की पुष्टि नहीं हो सकी।"
                        if hindi
                        else "Available jaankari se is hisse ko verify nahi kar saka."
                        if hinglish
                        else "I couldn’t verify whether this is safe from the sources available. The safety assessment remains unresolved."
                        if task.domain in {"health", "animal_health"}
                        else "I couldn’t verify the applicable legal procedure for this part of your request."
                        if task.intent == "legal_options"
                        else "I couldn’t complete this part reliably with the available information."
                    )
            if len(visible_units) > 1 and not (
                idx == 0 and task.intent == "case_update" and unit.claims
            ):
                hi_labels = {
                    "draft": "मसौदा",
                    "revision": "संशोधित मसौदा",
                    "summary": "तथ्यों का सारांश",
                    "evidence": "ज़रूरी प्रमाण",
                    "legal_options": "अगले कदम",
                    "search": "जानकारी की खोज",
                }
                label = (
                    hi_labels.get(task.intent, "आपका सवाल")
                    if hindi
                    else LABELS.get(task.intent, "Requested help")
                )
                text = f"**{label}**\n\n{text}"
            pieces.append(text)
        if before_sending:
            pieces.append("\n\n".join(dict.fromkeys(before_sending)))
        if deferred_questions and not question_rendered:
            pieces.append(deferred_questions[0])
        if interpretation.invalid_tasks:
            pieces.append(
                "आपके अनुरोध का एक हिस्सा स्पष्ट नहीं समझ पाया। कृपया उसे अलग संदेश में लिखें।"
                if hindi
                else "I couldn’t reliably interpret part of your request. Please send that part separately; the assistance above remains available."
            )
        return {
            "response": "\n\n".join(pieces),
            "approved_documents": documents,
            "published_passage_ids": sorted(used),
            "assistance_status": "delivered"
            if units and all(u.status == "supported" for u in units)
            else "partial"
            if any(u.status in {"supported", "partial"} for u in units)
            else "deferred",
            "document_status": next(
                (
                    status
                    for status in ("needs_material_review", "needs_user_details", "prepared")
                    if any(u.document_status == status for u in units)
                ),
                "not_applicable",
            ),
            "legal_verification_status": "unresolved"
            if any(u.legal_verification_status == "unresolved" for u in units)
            else "supported"
            if any(u.legal_verification_status == "supported" for u in units)
            else "not_required",
            "publication_status": "supported"
            if units and all(u.status == "supported" for u in units)
            else "partial"
            if any(u.status in {"supported", "partial"} for u in units)
            else "deferred",
        }
