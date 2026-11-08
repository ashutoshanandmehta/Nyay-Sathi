"""Approved protective guidance and multidimensional urgent-risk routing independent of model availability."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

CONTACT = {
    "number": "112",
    "url": "https://www.mha.gov.in/emergency-response-support-system-erss",
    "checked_at": "2026-11-07",
    "revalidate_after": "2026-11-14",
    "jurisdiction": "India",
}

SPECIALIZED_CONTACTS = {
    "domestic_violence": {
        "number": "181",
        "url": "https://wcd.gov.in/",
        "checked_at": "2026-11-07",
        "revalidate_after": "2026-11-14",
        "jurisdiction": "India",
    },
    "self_harm": {
        "number": "14416",
        "url": "https://telemanas.mohfw.gov.in/",
        "checked_at": "2026-11-07",
        "revalidate_after": "2026-11-14",
        "jurisdiction": "India",
    },
    "financial_cyber_fraud": {
        "number": "1930",
        "url": "https://cybercrime.gov.in/",
        "checked_at": "2026-11-07",
        "revalidate_after": "2026-11-14",
        "jurisdiction": "India",
    },
    "medical_emergency": {
        "number": "108",
        "url": "https://www.mha.gov.in/emergency-response-support-system-erss",
        "checked_at": "2026-11-07",
        "revalidate_after": "2026-11-14",
        "jurisdiction": "India",
    },
}

TEXT = {
    "en": "If you are in immediate danger, prioritize your safety. Avoid physical confrontation or resisting custody. If safe, contact a trusted person and tell them where you are. Preserve messages and details once it is safe.",
    "hi": "यदि अभी खतरा है, पहले अपनी सुरक्षा पर ध्यान दें। शारीरिक टकराव या हिरासत का विरोध न करें। सुरक्षित हो तो किसी भरोसेमंद व्यक्ति को अपनी जगह बताएं और मदद मांगें। सुरक्षित होने पर संदेश और घटना के विवरण संभालें।",
    "hinglish": "Agar abhi khatra hai, pehle apni safety par dhyan dein. Physical confrontation ya custody ka resistance na karein. Safe ho to kisi trusted person ko apni location batayein. Safe hone ke baad messages aur incident details sambhal kar rakhein.",
}

SELF_HARM_TEXT = {
    "en": "Your life and safety matter right now. Please pause and reach out to someone you trust or a crisis counsellor immediately; you do not have to carry this alone.",
    "hi": "आपकी सुरक्षा और जीवन अभी सबसे महत्वपूर्ण हैं। कृपया तुरंत किसी भरोसेमंद व्यक्ति या मानसिक स्वास्थ्य सहायता सेवा से बात करें; आपको अकेले इसका सामना नहीं करना है।",
    "hinglish": "Aapki life aur safety abhi sabse zaroori hai. Please turant kisi trusted person ya crisis helpline se baat karein; aapko yeh akele face nahi karna hai.",
}

CYBER_FRAUD_TEXT = {
    "en": "Urgent financial-fraud alert: Act immediately to stop further unauthorized debits. Contact your bank or wallet's official fraud helpline right now to block compromised cards, UPI, wallet, and net-banking access, and get a complaint reference number. From a clean, trusted device, change compromised passwords/PINs and sign out of active sessions.",
    "hi": "तत्काल साइबर-वित्तीय धोखाधड़ी चेतावनी: आगे की अनधिकृत निकासी रोकने के लिए तुरंत कदम उठाएं। अपने बैंक या वॉलेट की आधिकारिक फ्रॉड हेल्पलाइन पर अभी कॉल करके कार्ड, UPI, वॉलेट और नेट-बैंकिंग एक्सेस ब्लॉक कराएं और शिकायत संख्या लें। किसी सुरक्षित डिवाइस से पासवर्ड/PIN बदलें और संदिग्ध सेशन लॉग-आउट करें।",
    "hinglish": "Urgent cyber-financial fraud alert: Aage ke unauthorized debits rokne ke liye turant action lein. Apne bank ya wallet ki official fraud helpline par abhi call karke compromised card, UPI, wallet aur net-banking block karayein aur complaint reference number lein. Trusted device se passwords/PIN badlein aur active sessions sign out karein.",
}

MEDICAL_TEXT = {
    "en": "Immediate medical emergency: Seek urgent in-person medical or hospital care right away and ask someone nearby to stay with you.",
    "hi": "तत्काल चिकित्सा आपात स्थिति: तुरंत नजदीकी अस्पताल या आपातकालीन चिकित्सा सहायता लें और किसी विश्वसनीय व्यक्ति को पास बुलाएं।",
    "hinglish": "Immediate medical emergency: Turant nazdeeki hospital ya emergency medical help lein aur kisi trusted person ko paas bulayein.",
}

INDIA_CUE_RE = re.compile(
    r"(?:₹|\brs\.?\s*\d|\binr\b|\bindia\b|\bindian\b|\bupi\b|\baadhaar\b|"
    r"\b(?:bengaluru|bangalore|vasanth\s*nagar|mumbai|delhi|new\s+delhi|chennai|hyderabad|"
    r"kolkata|pune|jaipur|ahmedabad|surat|lucknow|kochi|coimbatore|gurugram|gurgaon|noida|"
    r"chandigarh|bhopal|indore|patna|nagpur|kerala|karnataka|maharashtra|tamil\s+nadu|"
    r"telangana|gujarat|rajasthan|uttar\s+pradesh|west\s+bengal|haryana|punjab|bihar|odisha|assam|goa)\b|"
    r"\b(?:blinkit|zepto|swiggy|zomato|flipkart|myntra|meesho|goibibo|makemytrip|oyo|phonepe|paytm|bhim|rupay)\b|"
    r"[\u0900-\u097f])",
    re.I,
)

HYPOTHETICAL_RE = re.compile(
    r"\b(?:hypothetically|hypothetical|in a novel|what if|last year|years ago|not in danger|no immediate danger)\b",
    re.I,
)

SELF_HARM_RE = re.compile(
    r"(?:kill myself|end my life|commit suicide|want to die|self[- ]harm|suicidal right now|आत्महत्या|खुदकुशी)",
    re.I,
)

DOMESTIC_VIOLENCE_RE = re.compile(
    r"(?:(?:husband|partner|in-laws?|spouse|father|brother).{0,60}(?:beating|hitting|locked|threatening|assaulting|choking)|domestic violence.{0,40}(?:now|help|unsafe)|पति.{0,40}(?:मार|धमक)|ससुराल.{0,40}(?:मार|बंद))",
    re.I | re.S,
)

EMERGENCY_COERCION_RE = re.compile(
    r"(?:police|officers?).{0,100}(?:entered|here|demand|detain|threat|won.t let|bribe|extort|harass)|"
    r"(?:threat|kill|beating|locked|blackmail|kidnap|abduct|unlawful detention).{0,60}(?:now|outside|here|me|room)|"
    r"(?:in immediate danger|being attacked|cannot leave|won.t let me leave|forced marriage now)|"
    r"पुलिस.{0,60}(?:पैसे|धमक|कमरे|हिरासत)|अभी.{0,30}(?:खतरा|मार|धमकी)",
    re.I | re.S,
)

CYBER_FINANCIAL_FRAUD_RE = re.compile(
    r"(?:(?:debited|withdrawn|deducted|drained|stolen|transferred\s+without|unauthorized\s+transaction|unauthorised\s+transaction)"
    r".{0,160}(?:scam|fraud|phishing|fake|link|whatsapp|otp|pin|password|wallet|upi|blocked\s+my\s+number|customer\s+care|anydesk|apk))|"
    r"(?:(?:fake\s+(?:customer\s+care|support|executive|helpline)|phishing\s+link|screen\s*shar\w*|anydesk|malicious\s+link|"
    r"enter(?:ed)?\s+(?:my\s+)?(?:password|pin|otp|mpin))"
    r".{0,220}(?:debited|withdrawn|deducted|drained|lost\s+₹|lost\s+rs|unauthorized|unauthorised|fraud|scam|blocked\s+my\s+number))|"
    r"(?:\b(?:cyber\s*fraud|upi\s*fraud|upi\s*scam|phishing\s*scam|bank\s*fraud)\b.{0,120}\b(?:debited|lost|stole|₹|rs\.?|bank|account|wallet)\b)|"
    r"(?:खाते\s+से.{0,60}(?:कट|निकल|धोखाधड़ी|फ्रॉड)|फर्जी\s+कस्टमर\s+केयर)",
    re.I | re.S,
)

MEDICAL_EMERGENCY_RE = re.compile(
    r"(?:bleeding\s+heavily|unconscious\s+right\s+now|heart\s+attack\s+now|poisoned\s+right\s+now|need\s+an?\s+ambulance\s+now)",
    re.I,
)

URGENT_FOLLOWUP_CUE_RE = re.compile(
    r"\b(?:fake|impersonat\w*|officers?|police|cops|uniform|badge|id card|warrant|station|"
    r"bribe|money|cash|upi|hotel|room|cctv|reception|left|outside|came back|scared|threat\w*|detain\w*|"
    r"what\s+should\s+i\s+(?:say|tell|do|ask)|what\s+to\s+(?:say|tell|do)|"
    r"how\s+(?:do|should)\s+i\s+(?:say|talk|speak|report|explain)|talking\s+points?|complaint|statement)\b|"
    r"^\s*(?:what|huh|how|why|explain|and\s+then|now\s+what)\s*\??\s*$|"
    r"(?:नकली|पुलिस|अफसर|वर्दी|पैसे|होटल|सीसीटीवी|थाने|क्या\s+बोलूं|क्या\s+कहूं)",
    re.I,
)


def detect_india_context(message: str, memory: dict[str, Any] | None = None) -> bool:
    if INDIA_CUE_RE.search(message or ""):
        return True
    if not memory:
        return False
    for k, f in (memory.get("facts") or {}).items():
        if isinstance(f, dict):
            val = str(f.get("value", ""))
            if k in {"transaction_country", "country", "jurisdiction"} and val.casefold() == "india":
                return True
            if INDIA_CUE_RE.search(val):
                return True
    return False


def detect_urgent_category(message: str) -> str | None:
    lower = message.casefold()
    if HYPOTHETICAL_RE.search(lower):
        return None
    if SELF_HARM_RE.search(lower):
        return "self_harm"
    if DOMESTIC_VIOLENCE_RE.search(lower):
        return "domestic_violence"
    if EMERGENCY_COERCION_RE.search(lower):
        return "physical_safety"
    if CYBER_FINANCIAL_FRAUD_RE.search(lower):
        return "financial_cyber_fraud"
    if MEDICAL_EMERGENCY_RE.search(lower):
        return "medical_emergency"
    return None


def is_physical_liberty_category(category: str | None) -> bool:
    return category in {"emergency", "physical_safety", "domestic_violence", "emergency_followup"}


def urgent_trigger(message: str) -> bool:
    # Deliberately conservative early help; not a legal classification gate.
    return detect_urgent_category(message) is not None


def _has_active_physical_urgent_case(
    memory: dict[str, Any] | None, prior_safety_messages: list[dict[str, Any]] | None
) -> bool:
    if prior_safety_messages:
        if any(
            m.get("category") in {None, "emergency", "physical_safety", "domestic_violence"}
            for m in prior_safety_messages
        ):
            return True
        if all(m.get("category") == "financial_cyber_fraud" for m in prior_safety_messages):
            return False
    if not memory:
        return False
    if memory.get("domain") == "criminal":
        return True
    blob = " ".join(
        str(v.get("value", "")) for v in (memory.get("facts") or {}).values() if isinstance(v, dict)
    ).casefold()
    return bool(
        re.search(
            r"\b(?:police|officer|bribe|extortion|detain|custody|room|threat|violence|coercion|112)\b",
            blob,
        )
    )


def classify_urgent_context(
    message: str,
    memory: dict[str, Any] | None = None,
    prior_safety_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Identify direct urgent turns (by risk mechanism) and physical-emergency follow-ups."""
    category = detect_urgent_category(message)
    already_warned = bool(prior_safety_messages)
    active_physical = _has_active_physical_urgent_case(memory, prior_safety_messages)
    followup = bool(
        not category
        and active_physical
        and not HYPOTHETICAL_RE.search(message.casefold())
        and URGENT_FOLLOWUP_CUE_RE.search(message)
    )
    guidance: list[str] = []
    if followup or category in {"emergency", "physical_safety"}:
        guidance = [
            "Do not confront or accuse suspected fake officers in person; move to a safe public/monitored area or stay with hotel management/trusted witnesses.",
            "Ask hotel reception/security immediately to preserve lobby/corridor CCTV footage, visitor register entries, and intercom logs with exact timestamps.",
            "Write down physical details while fresh: names used, uniform/badge markings, vehicle number, phone numbers, and any UPI ID/account or cash demand details.",
            "Verify whether any legitimate police team was dispatched by calling 112 (ERSS) or the local police control room from a safe phone.",
            "When speaking at a police station or control room, stay calm, ask for the Duty Officer or Station House Officer (SHO), state chronological facts you personally observed without speculating, and request a written acknowledgement or diary reference.",
        ]
    elif category == "financial_cyber_fraud":
        guidance = [
            "Call 1930 (India's National Cyber-Financial Fraud Helpline) immediately to report the unauthorized transactions and suspect details for fund-freeze coordination.",
            "Call your bank and wallet's official fraud helpline immediately to block compromised payment access and obtain a formal dispute/complaint reference number.",
            "From a clean, trusted device, reset wallet, banking, and email passwords/PINs, revoke active sessions, and remove any app installed via the suspicious link.",
            "File the complete complaint on https://cybercrime.gov.in preserving UTR/transaction IDs, bank SMS alerts, WhatsApp chat screenshots, scammer number, and phishing URL.",
        ]
    return {
        "direct_urgent": category is not None,
        "category": category or ("emergency_followup" if followup else None),
        "urgent_continuation": followup
        or (is_physical_liberty_category(category) and already_warned),
        "emit_immediate_safety": (category is not None) and not already_warned,
        "verification_guidance": guidance,
    }


def _contact_verified(contact: dict[str, str], current: date) -> bool:
    return (
        date.fromisoformat(contact["checked_at"])
        <= current
        <= date.fromisoformat(contact["revalidate_after"])
    )


def safety_event(language="en", *, today=None, india=False, category="physical_safety"):
    language = language if language in TEXT else "en"
    normalized = "physical_safety" if category in {None, "emergency"} else category
    current = today or date.today()
    sources: list[str] = []

    if normalized == "financial_cyber_fraud":
        text = CYBER_FRAUD_TEXT[language]
        spec = SPECIALIZED_CONTACTS["financial_cyber_fraud"]
        if india and _contact_verified(spec, current):
            extra = {
                "en": " In India, call 1930 immediately (National Cyber-Financial Fraud Helpline) and report at cybercrime.gov.in with transaction IDs, phone numbers, and links.",
                "hi": " भारत में तुरंत 1930 (राष्ट्रीय साइबर-वित्तीय धोखाधड़ी हेल्पलाइन) पर कॉल करें और cybercrime.gov.in पर ट्रांज़ैक्शन ID, फोन नंबर व लिंक के साथ शिकायत दर्ज करें।",
                "hinglish": " India mein turant 1930 (National Cyber-Financial Fraud Helpline) par call karein aur cybercrime.gov.in par transaction IDs, phone numbers aur link ke saath report karein.",
            }
            text += extra[language]
            sources.append(spec["url"])
        return {
            "type": "safety",
            "category": "financial_cyber_fraud",
            "content_id": "safety-" + hashlib.sha256(text.encode()).hexdigest()[:16],
            "text": text,
            "sources": sources,
        }

    if normalized == "medical_emergency":
        text = MEDICAL_TEXT[language]
        spec = SPECIALIZED_CONTACTS["medical_emergency"]
        if india and _contact_verified(spec, current):
            extra = {
                "en": " In India, call 108 or 112 for an immediate ambulance/medical emergency.",
                "hi": " भारत में तत्काल एम्बुलेंस या चिकित्सा सहायता के लिए 108 या 112 पर कॉल करें।",
                "hinglish": " India mein immediate ambulance ya medical emergency ke liye 108 ya 112 par call karein.",
            }
            text += extra[language]
            sources.append(spec["url"])
        return {
            "type": "safety",
            "category": "medical_emergency",
            "content_id": "safety-" + hashlib.sha256(text.encode()).hexdigest()[:16],
            "text": text,
            "sources": sources,
        }

    base_map = SELF_HARM_TEXT if normalized == "self_harm" else TEXT
    text = base_map[language]

    verified_112 = _contact_verified(CONTACT, current)
    if india and verified_112:
        extra = {
            "en": " In India, call 112 for an immediate emergency if it is safe to call.",
            "hi": " भारत में तत्काल आपात स्थिति में, कॉल करना सुरक्षित हो तो 112 पर कॉल करें।",
            "hinglish": " India mein immediate emergency ho aur call karna safe ho to 112 par call karein.",
        }
        text += extra[language]
        sources.append(CONTACT["url"])

    if india and normalized in SPECIALIZED_CONTACTS:
        spec = SPECIALIZED_CONTACTS[normalized]
        if _contact_verified(spec, current):
            if normalized == "self_harm":
                spec_extra = {
                    "en": " For 24x7 mental-health crisis support in India, call Tele-MANAS at 14416.",
                    "hi": " भारत में 24x7 मानसिक स्वास्थ्य सहायता के लिए Tele-MANAS के 14416 पर कॉल करें।",
                    "hinglish": " India mein 24x7 mental-health crisis support ke liye Tele-MANAS par 14416 call karein.",
                }
            else:
                spec_extra = {
                    "en": " Women facing domestic violence or distress can also call the 181 Women Helpline if safe.",
                    "hi": " घरेलू हिंसा या संकट की स्थिति में सुरक्षित होने पर 181 महिला हेल्पलाइन पर भी कॉल कर सकती हैं।",
                    "hinglish": " Domestic violence ya distress mein safe hone par 181 Women Helpline par bhi call kar sakti hain.",
                }
            text += spec_extra[language]
            sources.append(spec["url"])

    return {
        "type": "safety",
        "category": normalized,
        "content_id": "safety-" + hashlib.sha256(text.encode()).hexdigest()[:16],
        "text": text,
        "sources": sources,
    }
