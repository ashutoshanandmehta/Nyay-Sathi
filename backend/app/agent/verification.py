"""Risk-calibrated verification: mechanical consistency, pinpoint statutory checks, and stage gates."""

import re
from urllib.parse import urlparse

TEMPLATES = {
    "greeting": {
        "en": "Tell me what happened, or ask your legal question. I can help you understand the issue and prepare your next step.",
        "hi": "बताइए क्या हुआ, या अपना कानूनी सवाल पूछिए। मैं बात समझने और अगला कदम तैयार करने में मदद कर सकता हूँ।",
        "hinglish": "Batayein kya hua, ya apna legal question poochhein. Main issue samajhne aur next step prepare karne mein madad kar sakta hoon.",
    },
    "preserve_records": {
        "en": "Keep the original documents, messages and payment records relevant to this issue. Make dated copies and a short chronology; avoid editing the originals.",
        "hi": "इस मामले के मूल दस्तावेज़, संदेश और भुगतान रिकॉर्ड संभालें। तारीख वाली प्रतियां और घटनाक्रम बनाएं; मूल रिकॉर्ड न बदलें।",
        "hinglish": "Is issue ke original documents, messages aur payment records sambhal kar rakhein. Dated copies aur short timeline banayein; originals edit na karein.",
    },
    "cyber_fraud_emergency_steps": {
        "en": "1. Call your bank or wallet's official fraud helpline immediately to block compromised access and record a complaint reference number.\n2. From a clean, trusted device, change compromised passwords/PINs and sign out of active sessions.\n3. Preserve all transaction IDs/UTRs, SMS alerts, WhatsApp screenshots, suspect phone numbers, and phishing links without editing originals.",
        "hi": "1. अपने बैंक या वॉलेट की आधिकारिक फ्रॉड हेल्पलाइन पर तुरंत कॉल करके एक्सेस ब्लॉक कराएं और शिकायत संख्या लें।\n2. किसी सुरक्षित डिवाइस से पासवर्ड/PIN बदलें और सक्रिय सेशन लॉग-आउट करें।\n3. सभी ट्रांज़ैक्शन ID/UTR, बैंक SMS, WhatsApp स्क्रीनशॉट, संदिग्ध नंबर और लिंक सुरक्षित रखें।",
        "hinglish": "1. Apne bank ya wallet ki official fraud helpline par turant call karke compromised access block karayein aur complaint reference number lein.\n2. Clean trusted device se passwords/PINs badlein aur active sessions sign out karein.\n3. Sabhi transaction IDs/UTRs, SMS alerts, WhatsApp screenshots, scammer phone numbers aur phishing links bina edit kiye preserve karein.",
    },
    "limited_research": {
        "en": "I could not verify the legal details needed for a reliable conclusion in this turn. The supported facts and preparation below are still available; a specific legal route needs further source checking.",
        "hi": "इस बार विश्वसनीय कानूनी निष्कर्ष के लिए ज़रूरी विवरण सत्यापित नहीं हो सके। उपलब्ध तथ्य और तैयारी उपयोगी हैं; किसी खास कानूनी रास्ते के लिए स्रोतों की और जांच चाहिए।",
        "hinglish": "Is turn mein reliable legal conclusion ke liye zaroori details verify nahi ho sakin. Available facts aur preparation useful hain; specific legal route ke sources aur check karne honge.",
    },
    # Runtime referrals closing crisis, safety and liberty turns; they name help without asserting eligibility.
    "handoff_liberty": {
        "en": "Because someone's liberty is involved, speak to a criminal lawyer as soon as you can, ideally before any bail hearing or before giving a statement. If paying a lawyer is difficult, ask the District Legal Services Authority (DLSA) at the district court whether you qualify for free legal aid.",
        "hi": "क्योंकि किसी की आज़ादी का सवाल है, जितनी जल्दी हो सके किसी आपराधिक मामलों के वकील से बात करें, बेहतर हो कि ज़मानत की सुनवाई या कोई बयान देने से पहले। अगर वकील की फीस देना मुश्किल है, तो ज़िला अदालत में ज़िला विधिक सेवा प्राधिकरण (DLSA) से पूछें कि क्या आप मुफ़्त कानूनी सहायता के पात्र हैं।",
        "hinglish": "Kyunki kisi ki azaadi ka sawal hai, jitni jaldi ho sake kisi criminal lawyer se baat karein, behtar ho ki bail hearing ya koi statement dene se pehle. Agar lawyer ki fees dena mushkil hai, to district court mein District Legal Services Authority (DLSA) se poochhein ki kya aap free legal aid ke liye eligible hain.",
    },
    "handoff_safety": {
        "en": "Once you are safe, a lawyer can help you get legal protection. If paying a lawyer is difficult, ask the District Legal Services Authority (DLSA) whether you qualify for free legal aid.",
        "hi": "सुरक्षित होने के बाद, एक वकील आपको कानूनी सुरक्षा दिलाने में मदद कर सकता है। अगर वकील की फीस देना मुश्किल है, तो ज़िला विधिक सेवा प्राधिकरण (DLSA) से पूछें कि क्या आप मुफ़्त कानूनी सहायता के पात्र हैं।",
        "hinglish": "Safe hone ke baad, ek lawyer aapko legal protection dilane mein madad kar sakta hai. Agar lawyer ki fees dena mushkil hai, to District Legal Services Authority (DLSA) se poochhein ki kya aap free legal aid ke liye eligible hain.",
    },
    "handoff_crisis": {
        "en": "You don't have to face this alone. Please talk to someone you trust and a trained counsellor right now. When you feel ready, a lawyer or the District Legal Services Authority (DLSA) can help with the legal problem behind this.",
        "hi": "आपको इसका सामना अकेले नहीं करना है। कृपया अभी किसी भरोसेमंद व्यक्ति और किसी प्रशिक्षित काउंसलर से बात करें। जब आप तैयार हों, तब कोई वकील या ज़िला विधिक सेवा प्राधिकरण (DLSA) इसके पीछे की कानूनी समस्या में मदद कर सकता है।",
        "hinglish": "Aapko iska saamna akele nahi karna hai. Please abhi kisi bharosemand vyakti aur kisi trained counsellor se baat karein. Jab aap ready hon, tab koi lawyer ya District Legal Services Authority (DLSA) iske peeche ki legal problem mein madad kar sakta hai.",
    },
    "no_verified_answer": {
        "en": "I couldn't verify enough reliable legal information to answer this safely just now, so I haven't given a legal conclusion. You can ask again with a few more details (your state, the dates, and what papers you have), or speak to a local lawyer or your District Legal Services Authority.",
        "hi": "अभी मैं इसका सुरक्षित जवाब देने लायक भरोसेमंद कानूनी जानकारी सत्यापित नहीं कर सका, इसलिए मैंने कोई कानूनी निष्कर्ष नहीं दिया है। आप थोड़ी और जानकारी (आपका राज्य, तारीखें और आपके पास कौन से कागज़ हैं) के साथ फिर से पूछ सकते हैं, या किसी स्थानीय वकील या अपने ज़िला विधिक सेवा प्राधिकरण से बात कर सकते हैं।",
        "hinglish": "Abhi main iska safe jawab dene layak reliable legal information verify nahi kar paya, isliye maine koi legal conclusion nahi diya hai. Aap thodi aur details (aapka state, dates, aur aapke paas kaun se papers hain) ke saath dobara pooch sakte hain, ya kisi local lawyer ya apne District Legal Services Authority se baat kar sakte hain.",
    },
    "configuration": {
        "en": "AI configuration required: Your message is saved in this chat. Add the backend OpenAI configuration to enable researched answers. You can still organize documents and export your case.",
        "hi": "AI configuration required: आपका संदेश इस चैट में सुरक्षित है। शोध वाले जवाब चालू करने के लिए backend में OpenAI सेटअप करें। दस्तावेज़ व्यवस्थित करना और केस एक्सपोर्ट करना उपलब्ध है।",
        "hinglish": "AI configuration required: Aapka message is chat mein saved hai. Researched answers ke liye backend OpenAI configure karein. Documents organize aur case export kar sakte hain.",
    },
}

# Detects disguised legal assertions, statutory provisions, mandatory legal deadlines,
# helpline numbers, or physical confrontation instructions inside practical/factual claims.
DISGUISED_CONSEQUENTIAL_RE = re.compile(
    r"(?:\b(?:section|sec\.|article|rule\s+\d+|order\s+(?!id\b)[ivxlcdm\d]+\b|act,\s*\d{4}|bns|bnss|bsa|ipc|crpc|cpa\s*2019)\b|"
    r"\b(?:must\s+(?:refund|pay|register|accept|release)|legally\s+(?:entitled|required|bound|mandatory)|"
    r"statutory\s+(?:right|deadline|limit)|limitation\s+period|"
    r"within\s+\d+\s*(?:days?|hours?|months?|years?)\s+(?:under|by\s+law|from\s+cause))\b|"
    r"\b(?:confront\s+them|physically\s+resist|refuse\s+custody|block\s+the\s+police)\b|"
    r"\b(?:call\s+\d{3,5}|helpline\s+\d{3,5}|\+?91[-\s]?\d{10})\b)",
    re.I,
)

# Labels do not prove meaning: precedent, ruling, time-limit and entitlement language goes to the
# independent reviewer even when the model tags the claim "practical".
REVIEW_REQUIRED_RE = re.compile(
    r"\b(?:courts?|commissions?|tribunals?|forums?|bench|judges?|magistrates?)\b.{0,60}"
    r"\b(?:held|holds|ruled|rules|ordered|directed|awarded|decided|struck|upheld|quashed)\b|"
    r"\b(?:precedents?|rulings?|judg(?:e)?ments?|verdicts?|case\s+law|landmark|in\s+similar\s+cases|courts?\s+have)\b|"
    r"\b\d+\s*(?:days?|weeks?|months?|years?|din)\b|"
    r"\b(?:double|twice|triple)\s+the\b|\d+(?:\.\d+)?\s*%|"
    r"\b(?:entitled|illegal|unlawful|offen[cs]es?|punishable|bailable|non-bailable|compoundable|liable|penalty|fine\s+of)\b|"
    r"धारा|अदालत|न्यायालय|फैसला|कानूनन|अवैध|जुर्माना|दोगुना|\d+\s*दिन",
    re.I,
)
CASE_NAME_RE = re.compile(r"\b[A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*)*\s+(?:v\.|vs\.?|versus)\s+[A-Z]")

SECTION_REF_RE = re.compile(
    r"\b(?:sections?|secs?\.)\s*(\d+[A-Za-z]?)(?:\(\d+\))?(?:\s*(?:,|and|&|to|-|–)\s*(\d+[A-Za-z]?)(?:\(\d+\))?)?",
    re.I,
)

PCA_SEVEN_DAY_PROVISO_RE = re.compile(
    r"\b(?:seven[- ]day|7[- ]day|within\s+(?:seven|7)\s+days)\b",
    re.I,
)

PCA_BRIBE_CONTEXT_RE = re.compile(
    r"\b(?:prevention\s+of\s+corruption|undue\s+advantage|compelled\s+to\s+(?:give|pay)|bribe|anti[- ]corruption)\b",
    re.I,
)

EXHAUSTED_GRIEVANCE_MSG_RE = re.compile(
    r"\bgrievance\s+(?:team|officer|cell|desk)\b.{0,120}\b(?:redirect\w*|closed|ignored|no\s+response|unresolved|refused|rejected)\b",
    re.I | re.S,
)

EXTERNAL_CONSUMER_ESCALATION_RE = re.compile(
    r"\b(?:national\s+consumer\s+helpline|nch\b|1915\b|consumerhelpline|consumer\s+commission|"
    r"district\s+commission|e-?jagriti|e-?daakhil|ombudsman|1930\b|cybercrime)\b",
    re.I,
)


def template_text(identifier, language):
    return TEMPLATES[identifier].get(language, TEMPLATES[identifier]["en"])


def _is_certified_or_official_public_entry(entry: dict) -> bool:
    if entry.get("generic_snippet"):
        return False
    if entry.get("certified_proposition") or entry.get("origin_verified"):
        return True
    if entry.get("source_type") == "indian_official":
        return True
    host = (urlparse(entry.get("canonical_url", "")).hostname or "").lower()
    return host.endswith((".gov.in", ".nic.in")) or host in {
        "rbi.org.in",
        "www.rbi.org.in",
        "sebi.gov.in",
    }


def has_disguised_consequential_assertion(text: str) -> bool:
    return bool(DISGUISED_CONSEQUENTIAL_RE.search(text or ""))


def needs_semantic_review(text: str) -> bool:
    """True when wording may assert law, precedent or deadlines, so no deterministic approval."""
    text = text or ""
    return (
        has_disguised_consequential_assertion(text)
        or bool(REVIEW_REQUIRED_RE.search(text))
        or bool(CASE_NAME_RE.search(text))
    )


def _extract_sections(text: str) -> set[str]:
    out: set[str] = set()
    for m in SECTION_REF_RE.finditer(text or ""):
        if m.group(1):
            out.add(m.group(1).upper())
        if m.group(2):
            out.add(m.group(2).upper())
    return out


def check_pinpoint_statutory_alignment(claim, registry) -> str | None:
    """Block statutory claims that attribute a section or proviso to the wrong statutory passage."""
    public_ids = registry.public_ids()
    cited_public = [registry.entries[k] for k in claim.evidence_ids if k in public_ids]
    if not cited_public:
        return None

    text = claim.text or ""
    # Specific high-risk statutory confusion: PCA Section 8(1) 7-day compulsion proviso cited as Section 7
    if PCA_SEVEN_DAY_PROVISO_RE.search(text) and PCA_BRIBE_CONTEXT_RE.search(text):
        has_section_8_source = any(
            "8" in _extract_sections((e.get("locator") or "") + " " + (e.get("text") or ""))
            for e in cited_public
        )
        if not has_section_8_source:
            return "pinpoint_locator_mismatch"

    claimed_sections = _extract_sections(text)
    if not claimed_sections:
        return None

    source_sections: set[str] = set()
    for entry in cited_public:
        source_sections |= _extract_sections(
            (entry.get("locator") or "") + " " + (entry.get("text") or "")
        )

    if source_sections and not (claimed_sections <= source_sections):
        return "pinpoint_locator_mismatch"
    return None


def check_exhausted_channel_progression(answer, message: str = "") -> str | None:
    """Detect when internal support + Grievance Officer are exhausted but no external route is given."""
    plan = getattr(answer, "action_plan", None)
    exhausted = {x.casefold() for x in (plan.exhausted_channels if plan else [])}
    grievance_exhausted = (
        (plan is not None and plan.dispute_stage == "internal_grievance_exhausted")
        or any("grievance" in x for x in exhausted)
        or bool(EXHAUSTED_GRIEVANCE_MSG_RE.search(message or ""))
    )
    if not grievance_exhausted:
        return None

    combined = " ".join(
        [c.text for c in answer.claims if c.text] + [answer.next_action or ""]
    )
    if not EXTERNAL_CONSUMER_ESCALATION_RE.search(combined):
        return (
            "Internal support and Grievance Officer have already been attempted without resolution; "
            "provide the next external escalation route (such as National Consumer Helpline 1915 / "
            "consumerhelpline.gov.in and District Consumer Commission via e-Jagriti) instead of "
            "merely restating internal Grievance Officer rules."
        )
    return None


TERMINAL_PUNCTUATION = {".", "?", "!", ":", ")", "”", '"', "]", "।"}


def is_sentence_complete(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if all(re.match(r"^(?:[-*•]|\d+[.)]|\||#+)\s*", line) for line in lines):
        return True
    if all(line.startswith("|") for line in lines):
        return True
    if stripped.startswith("#"):
        return True
    return stripped[-1] in TERMINAL_PUNCTUATION


class PendingList(list):
    """List of pending claim IDs that also supports mapping access to pending reasons."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reasons: dict[str, str] = {}

    def append_reason(self, claim_id: str, reason: str):
        self.append(claim_id)
        self._reasons[claim_id] = reason

    def get(self, key, default=None):
        return self._reasons.get(key, default)

    def __getitem__(self, item):
        if isinstance(item, str):
            return self._reasons[item]
        return super().__getitem__(item)


def mechanical_checks(answer, registry):
    """Return blocked reasons, risk-calibrated deterministic approvals, and claims needing review."""
    blocked, approved, pending = {}, {}, PendingList()
    ids = {c.claim_id for c in answer.claims}
    public_ids = registry.public_ids()

    risk_types = set(getattr(answer, "risk_types", None) or [])
    if getattr(answer, "action_plan", None) and answer.action_plan.risk_types:
        risk_types |= set(answer.action_plan.risk_types)
    non_physical_urgency = bool(risk_types) and risk_types <= {
        "financial_fraud",
        "digital_compromise",
        "deadline_risk",
        "legal_uncertainty",
    }
    physical_liberty_urgent = (answer.risk == "urgent") and not non_physical_urgency

    for claim in answer.claims:
        reason = None
        needs_legal_authority = (
            claim.kind in {"legal", "procedure", "safety"}
            or claim.grounding == "verified_legal_source"
        )
        if any(k not in registry.entries for k in claim.evidence_ids):
            reason = "unknown_evidence"
        elif any(k not in ids or k == claim.claim_id for k in claim.depends_on):
            reason = "invalid_dependency"
        elif re.search(
            r"https?://|\[Source:|\]\(|\b(?:I (?:have )?(?:filed|sent|saved|signed|updated)|I am (?:your |a )?(?:lawyer|advocate))\b",
            claim.text,
            re.I,
        ):
            reason = "untrusted_link_or_execution_claim"
        elif needs_legal_authority and not any(k in public_ids for k in claim.evidence_ids):
            reason = "missing_public_evidence"
        elif (
            claim.kind in {"legal", "procedure"} or claim.grounding == "verified_legal_source"
        ) and not any(
            _is_certified_or_official_public_entry(registry.entries[k])
            for k in claim.evidence_ids
            if k in public_ids
        ):
            reason = "uncertified_or_generic_legal_source"
        elif (pinpoint_err := check_pinpoint_statutory_alignment(claim, registry)) is not None:
            reason = pinpoint_err
        elif (
            claim.kind not in {"template", "question", "limitation"}
            and not claim.evidence_ids
            and not (
                claim.kind == "practical"
                and claim.grounding == "practical_precaution"
                and not claim.in_document
                and not has_disguised_consequential_assertion(claim.text)
            )
        ):
            reason = "missing_claim_evidence"

        if (
            reason == "missing_claim_evidence"
            and claim.in_document
            and claim.kind in {"document", "practical"}
            and claim.grounding == "practical_precaution"
        ):
            # A requested draft with [placeholders] often cites no fact; the reviewer judges it
            # (and repair can add the user's segment IDs) instead of it vanishing unseen.
            pending.append_reason(claim.claim_id, "draft without cited facts")
        elif reason:
            blocked[claim.claim_id] = reason
        elif claim.kind == "template":
            if claim.template_id in TEMPLATES and not claim.text and not claim.in_document:
                approved[claim.claim_id] = "approved_template"
            else:
                blocked[claim.claim_id] = "invalid_template"
        elif not is_sentence_complete(claim.text):
            pending.append_reason(claim.claim_id, "unfinished sentence")
        elif claim.kind == "quote":
            private = [registry.entries[k] for k in claim.evidence_ids if k not in public_ids]
            if (
                claim.text.strip()
                and any(claim.text in e["text"] for e in private)
                and len(claim.text) <= 3000
            ):
                approved[claim.claim_id] = "attributed_exact_extract"
            else:
                blocked[claim.claim_id] = "quote_not_in_private_evidence"
        elif (
            not physical_liberty_urgent
            and claim.grounding in {"reported_by_user", "practical_precaution"}
            and claim.kind in {"factual", "practical", "document"}
            and claim.block_type not in {"recommended_route", "human_handoff"}
            and claim.text.strip()
            and not needs_semantic_review(claim.text)
            and all(k in registry.entries and k not in public_ids for k in claim.evidence_ids)
        ):
            # Risk-calibrated publication: user-attributed facts, practical preparation, and
            # placeholder-safe factual drafts publish after deterministic consistency checks.
            approved[claim.claim_id] = "risk_calibrated_consistency"
        elif (
            not physical_liberty_urgent
            and claim.kind == "question"
            and claim.grounding == "requires_confirmation"
            and "?" in claim.text
            and len(claim.text) <= 400
            and not needs_semantic_review(claim.text)
        ):
            approved[claim.claim_id] = "non_assertive_clarification"
        else:
            # High-impact route recommendations, legal propositions, physical-liberty claims,
            # and untagged free prose require independent semantic review.
            pending.append(claim.claim_id)
    return blocked, approved, pending


def propagate_dependencies(answer, accepted):
    """Cycles and dependents on rejected claims cannot be published."""
    accepted = dict(accepted)
    done = set()
    while True:
        ready = [
            c.claim_id
            for c in answer.claims
            if c.claim_id in accepted and c.claim_id not in done and set(c.depends_on) <= done
        ]
        if not ready:
            break
        done.update(ready)
    return {key: value for key, value in accepted.items() if key in done}
