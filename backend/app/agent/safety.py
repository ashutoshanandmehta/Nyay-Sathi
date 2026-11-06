"""Approved protective guidance is independent of research and model availability."""

import hashlib
import re
from datetime import date

CONTACT = {
    "number": "112",
    "url": "https://www.mha.gov.in/emergency-response-support-system-erss",
    "checked_at": "2026-11-07",
    "revalidate_after": "2026-11-14",
    "jurisdiction": "India",
}

TEXT = {
    "en": "If you are in immediate danger, prioritize your safety. Avoid physical confrontation or resisting custody. If safe, contact a trusted person and tell them where you are. Preserve messages and details once it is safe.",
    "hi": "यदि अभी खतरा है, पहले अपनी सुरक्षा पर ध्यान दें। शारीरिक टकराव या हिरासत का विरोध न करें। सुरक्षित हो तो किसी भरोसेमंद व्यक्ति को अपनी जगह बताएं और मदद मांगें। सुरक्षित होने पर संदेश और घटना के विवरण संभालें।",
    "hinglish": "Agar abhi khatra hai, pehle apni safety par dhyan dein. Physical confrontation ya custody ka resistance na karein. Safe ho to kisi trusted person ko apni location batayein. Safe hone ke baad messages aur incident details sambhal kar rakhein.",
}


def urgent_trigger(message):
    # Deliberately conservative early help; not a legal classification gate.
    lower = message.casefold()
    if re.search(
        r"\b(?:hypothetically|hypothetical|in a novel|what if|last year|years ago|not in danger|no immediate danger)\b",
        lower,
    ):
        return False
    return bool(
        re.search(
            r"(?:police|officers?).{0,100}(?:entered|here|demand|detain|threat|won.t let)|(?:threat|kill|beating|locked|blackmail).{0,60}(?:now|outside|here|me)|(?:in immediate danger|being attacked|cannot leave|won.t let me leave)|पुलिस.{0,60}(?:पैसे|धमक|कमरे)|अभी.{0,30}(?:खतरा|मार|धमकी)",
            lower,
            re.S,
        )
    )


def safety_event(language="en", *, today=None, india=False):
    language = language if language in TEXT else "en"
    text = TEXT[language]
    current = today or date.today()
    verified = (
        date.fromisoformat(CONTACT["checked_at"])
        <= current
        <= date.fromisoformat(CONTACT["revalidate_after"])
    )
    if india and verified:
        extra = {
            "en": " In India, call 112 for an immediate emergency if it is safe to call.",
            "hi": " भारत में तत्काल आपात स्थिति में, कॉल करना सुरक्षित हो तो 112 पर कॉल करें।",
            "hinglish": " India mein immediate emergency ho aur call karna safe ho to 112 par call karein.",
        }
        text += extra[language]
    return {
        "type": "safety",
        "content_id": "safety-" + hashlib.sha256(text.encode()).hexdigest()[:16],
        "text": text,
        "sources": [CONTACT["url"]] if india and verified else [],
    }
