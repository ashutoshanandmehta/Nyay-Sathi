"""Mechanical checks never masquerade as semantic legal verification."""

import re

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
    "limited_research": {
        "en": "I could not verify the legal details needed for a reliable conclusion in this turn. The supported facts and preparation below are still available; a specific legal route needs further source checking.",
        "hi": "इस बार विश्वसनीय कानूनी निष्कर्ष के लिए ज़रूरी विवरण सत्यापित नहीं हो सके। उपलब्ध तथ्य और तैयारी उपयोगी हैं; किसी खास कानूनी रास्ते के लिए स्रोतों की और जांच चाहिए।",
        "hinglish": "Is turn mein reliable legal conclusion ke liye zaroori details verify nahi ho sakin. Available facts aur preparation useful hain; specific legal route ke sources aur check karne honge.",
    },
    "configuration": {
        "en": "AI configuration required: Your message is saved in this chat. Add the backend OpenAI configuration to enable researched answers. You can still organize documents and export your case.",
        "hi": "AI configuration required: आपका संदेश इस चैट में सुरक्षित है। शोध वाले जवाब चालू करने के लिए backend में OpenAI सेटअप करें। दस्तावेज़ व्यवस्थित करना और केस एक्सपोर्ट करना उपलब्ध है।",
        "hinglish": "AI configuration required: Aapka message is chat mein saved hai. Researched answers ke liye backend OpenAI configure karein. Documents organize aur case export kar sakte hain.",
    },
}


def template_text(identifier, language):
    return TEMPLATES[identifier].get(language, TEMPLATES[identifier]["en"])


def mechanical_checks(answer, registry):
    """Return blocked reasons, deterministic approvals, and prose requiring review."""
    blocked, approved, pending = {}, {}, []
    ids = {c.claim_id for c in answer.claims}
    for claim in answer.claims:
        reason = None
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
        elif claim.kind in {"legal", "procedure", "safety"} and not any(
            k in registry.public_ids() for k in claim.evidence_ids
        ):
            reason = "missing_public_evidence"
        elif claim.kind not in {"template", "question", "limitation"} and not claim.evidence_ids:
            reason = "missing_claim_evidence"
        if reason:
            blocked[claim.claim_id] = reason
        elif claim.kind == "template":
            if claim.template_id in TEMPLATES and not claim.text and not claim.in_document:
                approved[claim.claim_id] = "approved_template"
            else:
                blocked[claim.claim_id] = "invalid_template"
        elif claim.kind == "quote":
            private = [
                registry.entries[k] for k in claim.evidence_ids if k not in registry.public_ids()
            ]
            if (
                claim.text.strip()
                and any(claim.text in e["text"] for e in private)
                and len(claim.text) <= 3000
            ):
                approved[claim.claim_id] = "attributed_exact_extract"
            else:
                blocked[claim.claim_id] = "quote_not_in_private_evidence"
        else:
            # Includes recommendations, deadlines hidden in drafts, and questions.
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
