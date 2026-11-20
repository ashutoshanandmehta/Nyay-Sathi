// Approved protective guidance and multidimensional urgent-risk routing independent of model availability.
// Preserves date-bounded contact verification with injected clock and expiry suppression.

import type { Language } from './contracts.ts'
import { sha256Hex } from './crypto.ts'

export interface VerifiedContactRecord {
  id: string
  category: string
  jurisdiction: string
  label: string
  channel_type: 'phone' | 'whatsapp' | 'email' | 'portal'
  destination: string
  official_source_url: string
  checked_at: string
  revalidate_after: string
  retired: boolean
}

export const DEFAULT_VERIFIED_CONTACTS: Record<string, VerifiedContactRecord> = {
  physical_safety: {
    id: 'india-erss-112',
    category: 'physical_safety',
    jurisdiction: 'India',
    label: 'Emergency Response Support System (ERSS)',
    channel_type: 'phone',
    destination: '112',
    official_source_url: 'https://www.mha.gov.in/emergency-response-support-system-erss',
    checked_at: '2026-11-07',
    revalidate_after: '2026-11-14',
    retired: false,
  },
  domestic_violence: {
    id: 'india-women-181',
    category: 'domestic_violence',
    jurisdiction: 'India',
    label: 'Women Helpline',
    channel_type: 'phone',
    destination: '181',
    official_source_url: 'https://wcd.gov.in/',
    checked_at: '2026-11-07',
    revalidate_after: '2026-11-14',
    retired: false,
  },
  self_harm: {
    id: 'india-telemanas-14416',
    category: 'self_harm',
    jurisdiction: 'India',
    label: 'Tele-MANAS Mental Health Helpline',
    channel_type: 'phone',
    destination: '14416',
    official_source_url: 'https://telemanas.mohfw.gov.in/',
    checked_at: '2026-11-07',
    revalidate_after: '2026-11-14',
    retired: false,
  },
  financial_cyber_fraud: {
    id: 'india-cyber-1930',
    category: 'financial_cyber_fraud',
    jurisdiction: 'India',
    label: 'National Cyber-Financial Fraud Helpline',
    channel_type: 'phone',
    destination: '1930',
    official_source_url: 'https://cybercrime.gov.in/',
    checked_at: '2026-11-07',
    revalidate_after: '2026-11-14',
    retired: false,
  },
  medical_emergency: {
    id: 'india-ambulance-108',
    category: 'medical_emergency',
    jurisdiction: 'India',
    label: 'Emergency Ambulance Service',
    channel_type: 'phone',
    destination: '108',
    official_source_url: 'https://www.mha.gov.in/emergency-response-support-system-erss',
    checked_at: '2026-11-07',
    revalidate_after: '2026-11-14',
    retired: false,
  },
}

const TEXT: Record<Language, string> = {
  en: 'If you are in immediate danger, prioritize your safety. Avoid physical confrontation or resisting custody. If safe, contact a trusted person and tell them where you are. Preserve messages and details once it is safe.',
  hi: 'यदि अभी खतरा है, पहले अपनी सुरक्षा पर ध्यान दें। शारीरिक टकराव या हिरासत का विरोध न करें। सुरक्षित हो तो किसी भरोसेमंद व्यक्ति को अपनी जगह बताएं और मदद मांगें। सुरक्षित होने पर संदेश और घटना के विवरण संभालें।',
  hinglish:
    'Agar abhi khatra hai, pehle apni safety par dhyan dein. Physical confrontation ya custody ka resistance na karein. Safe ho to kisi trusted person ko apni location batayein. Safe hone ke baad messages aur incident details sambhal kar rakhein.',
}

const SELF_HARM_TEXT: Record<Language, string> = {
  en: 'Your life and safety matter right now. Please pause and reach out to someone you trust or a crisis counsellor immediately; you do not have to carry this alone.',
  hi: 'आपकी सुरक्षा और जीवन अभी सबसे महत्वपूर्ण हैं। कृपया तुरंत किसी भरोसेमंद व्यक्ति या मानसिक स्वास्थ्य सहायता सेवा से बात करें; आपको अकेले इसका सामना नहीं करना है।',
  hinglish:
    'Aapki life aur safety abhi sabse zaroori hai. Please turant kisi trusted person ya crisis helpline se baat karein; aapko yeh akele face nahi karna hai.',
}

const CYBER_FRAUD_TEXT: Record<Language, string> = {
  en: "Urgent financial-fraud alert: Act immediately to stop further unauthorized debits. Contact your bank or wallet's official fraud helpline right now to block compromised cards, UPI, wallet, and net-banking access, and get a complaint reference number. From a clean, trusted device, change compromised passwords/PINs and sign out of active sessions.",
  hi: 'तत्काल साइबर-वित्तीय धोखाधड़ी चेतावनी: आगे की अनधिकृत निकासी रोकने के लिए तुरंत कदम उठाएं। अपने बैंक या वॉलेट की आधिकारिक फ्रॉड हेल्पलाइन पर अभी कॉल करके कार्ड, UPI, वॉलेट और नेट-बैंकिंग एक्सेस ब्लॉक कराएं और शिकायत संख्या लें। किसी सुरक्षित डिवाइस से पासवर्ड/PIN बदलें और संदिग्ध सेशन लॉग-आउट करें।',
  hinglish:
    'Urgent cyber-financial fraud alert: Aage ke unauthorized debits rokne ke liye turant action lein. Apne bank ya wallet ki official fraud helpline par abhi call karke compromised card, UPI, wallet aur net-banking block karayein aur complaint reference number lein. Trusted device se passwords/PIN badlein aur active sessions sign out karein.',
}

const MEDICAL_TEXT: Record<Language, string> = {
  en: 'Immediate medical emergency: Seek urgent in-person medical or hospital care right away and ask someone nearby to stay with you.',
  hi: 'तत्काल चिकित्सा आपात स्थिति: तुरंत नजदीकी अस्पताल या आपातकालीन चिकित्सा सहायता लें और किसी विश्वसनीय व्यक्ति को पास बुलाएं।',
  hinglish:
    'Immediate medical emergency: Turant nazdeeki hospital ya emergency medical help lein aur kisi trusted person ko paas bulayein.',
}

const INDIA_CUE_RE =
  /(?:₹|\brs\.?\s*\d|\binr\b|\bindia\b|\bindian\b|\bupi\b|\baadhaar\b|\b(?:bengaluru|bangalore|vasanth\s*nagar|mumbai|delhi|new\s+delhi|chennai|hyderabad|kolkata|pune|jaipur|ahmedabad|surat|lucknow|kochi|coimbatore|gurugram|gurgaon|noida|chandigarh|bhopal|indore|patna|nagpur|kerala|karnataka|maharashtra|tamil\s+nadu|telangana|gujarat|rajasthan|uttar\s+pradesh|west\s+bengal|haryana|punjab|bihar|odisha|assam|goa)\b|\b(?:blinkit|zepto|swiggy|zomato|flipkart|myntra|meesho|goibibo|makemytrip|oyo|phonepe|paytm|bhim|rupay)\b|[\u0900-\u097f])/iu

const HYPOTHETICAL_RE =
  /\b(?:hypothetically|hypothetical|in a novel|what if|last year|years ago|not in danger|no immediate danger)\b/i

const SELF_HARM_RE =
  /(?:kill myself|end my life|commit suicide|want to die|self[- ]harm|suicidal right now|आत्महत्या|खुदकुशी)/iu

const DOMESTIC_VIOLENCE_RE =
  /(?:(?:husband|partner|in-laws?|spouse|father|brother)[\s\S]{0,60}(?:beating|hitting|locked|threatening|assaulting|choking)|domestic violence[\s\S]{0,40}(?:now|help|unsafe)|पति[\s\S]{0,40}(?:मार|धमक)|ससुराल[\s\S]{0,40}(?:मार|बंद))/iu

const EMERGENCY_COERCION_RE =
  /(?:police|officers?)[\s\S]{0,100}(?:entered|here|demand|detain|threat|won.t let|bribe|extort|harass)|(?:threat|kill|beating|locked|blackmail|kidnap|abduct|unlawful detention)[\s\S]{0,60}(?:now|outside|here|me|room)|(?:in immediate danger|being attacked|cannot leave|won.t let me leave|forced marriage now)|पुलिस[\s\S]{0,60}(?:पैसे|धमक|कमरे|हिरासत)|अभी[\s\S]{0,30}(?:खतरा|मार|धमकी)/iu

const COERCION_ENDED_RE =
  /\b(?:escaped|got\s+away|let\s+us\s+go|let\s+me\s+go|(?:they|we|i)\s+left|(?:we(?:'re|\s+are)|i(?:'m|\s+am))\s+(?:safe|home|back\s+home)\s+now|to\s+(?:escape|get\s+away))\b/i

const COERCION_ONGOING_RE =
  /\b(?:still|right\s+now|now|currently|won.t\s+(?:let|release)|not\s+(?:letting|releasing)|detained|in\s+custody|locked|outside\s+(?:our|my|the)\s+(?:room|door|house)|keep\s+(?:calling|threatening))\b/i

const CYBER_FINANCIAL_FRAUD_RE =
  /(?:(?:debited|withdrawn|deducted|drained|stolen|transferred\s+without|unauthorized\s+transaction|unauthorised\s+transaction)[\s\S]{0,160}(?:scam|fraud|phishing|fake|link|whatsapp|otp|pin|password|wallet|upi|blocked\s+my\s+number|customer\s+care|anydesk|apk))|(?:(?:fake\s+(?:customer\s+care|support|executive|helpline)|phishing\s+link|screen\s*shar\w*|anydesk|malicious\s+link|enter(?:ed)?\s+(?:my\s+)?(?:password|pin|otp|mpin))[\s\S]{0,220}(?:debited|withdrawn|deducted|drained|lost\s+₹|lost\s+rs|unauthorized|unauthorised|fraud|scam|blocked\s+my\s+number))|(?:\b(?:cyber\s*fraud|upi\s*fraud|upi\s*scam|phishing\s*scam|bank\s*fraud)\b[\s\S]{0,120}\b(?:debited|lost|stole|₹|rs\.?|bank|account|wallet)\b)|(?:खाते\s+से[\s\S]{0,60}(?:कट|निकल|धोखाधड़ी|फ्रॉड)|फर्जी\s+कस्टमर\s+केयर)/iu

const MEDICAL_EMERGENCY_RE =
  /(?:bleeding\s+heavily|unconscious\s+right\s+now|heart\s+attack\s+now|poisoned\s+right\s+now|need\s+an?\s+ambulance\s+now)/i

const URGENT_FOLLOWUP_CUE_RE =
  /\b(?:fake|impersonat\w*|officers?|police|cops|uniform|badge|id card|warrant|station|bribe|money|cash|upi|hotel|room|cctv|reception|left|outside|came back|scared|threat\w*|detain\w*|what\s+should\s+i\s+(?:say|tell|do|ask)|what\s+to\s+(?:say|tell|do)|how\s+(?:do|should)\s+i\s+(?:say|talk|speak|report|explain)|talking\s+points?|complaint|statement)\b|^\s*(?:what|huh|how|why|explain|and\s+then|now\s+what)\s*\??\s*$|(?:\u0928\u0915\u0932\u0940|\u092a\u0941\u0932\u093f\u0938|\u0905\u092b\u0938\u0930|\u0935\u0930\u094d\u0926\u0940|\u092a\u0948\u0938\u0947|\u0939\u094b\u091f\u0932|\u0938\u0940\u0938\u0940\u091f\u0940\u0935\u0940|\u0925\u093e\u0928\u0947|\u0915\u094d\u092f\u093e\s+\u092c\u094b\u0932\u0942\u0902|\u0915\u094d\u092f\u093e\s+\u0915\u0939\u0942\u0902)/iu

export function detectIndiaContext(message: string, memory?: Record<string, unknown> | null): boolean {
  if (INDIA_CUE_RE.test(message || '')) return true
  if (!memory) return false
  const facts = (memory.facts || {}) as Record<string, { value?: unknown }>
  for (const [key, fact] of Object.entries(facts)) {
    const val = String(fact?.value ?? '')
    if (['transaction_country', 'country', 'jurisdiction'].includes(key) && val.toLowerCase() === 'india') {
      return true
    }
    if (INDIA_CUE_RE.test(val)) return true
  }
  return false
}

export type UrgentCategory =
  | 'self_harm'
  | 'domestic_violence'
  | 'physical_safety'
  | 'financial_cyber_fraud'
  | 'medical_emergency'

export function detectUrgentCategory(message: string): UrgentCategory | null {
  const lower = (message || '').toLowerCase()
  if (HYPOTHETICAL_RE.test(lower)) return null
  if (SELF_HARM_RE.test(lower)) return 'self_harm'
  if (DOMESTIC_VIOLENCE_RE.test(lower)) return 'domestic_violence'
  if (EMERGENCY_COERCION_RE.test(lower) && (COERCION_ONGOING_RE.test(lower) || !COERCION_ENDED_RE.test(lower))) {
    return 'physical_safety'
  }
  if (CYBER_FINANCIAL_FRAUD_RE.test(lower)) return 'financial_cyber_fraud'
  if (MEDICAL_EMERGENCY_RE.test(lower)) return 'medical_emergency'
  return null
}

export function urgentTrigger(message: string): boolean {
  return detectUrgentCategory(message) !== null
}

export function isPhysicalLibertyCategory(category: string | null | undefined): boolean {
  return ['emergency', 'physical_safety', 'domestic_violence', 'emergency_followup'].includes(category || '')
}

function hasActivePhysicalUrgentCase(
  memory?: Record<string, unknown> | null,
  priorSafetyMessages?: Array<Record<string, unknown>> | null
): boolean {
  if (priorSafetyMessages && priorSafetyMessages.length > 0) {
    if (priorSafetyMessages.some(m => [undefined, null, 'emergency', 'physical_safety', 'domestic_violence'].includes(m.category as string))) {
      return true
    }
    if (priorSafetyMessages.every(m => m.category === 'financial_cyber_fraud')) {
      return false
    }
  }
  if (!memory) return false
  if (memory.domain === 'criminal') return true
  const facts = (memory.facts || {}) as Record<string, { value?: unknown }>
  const blob = Object.values(facts)
    .map(v => String(v?.value ?? ''))
    .join(' ')
    .toLowerCase()
  return /\b(?:police|officer|bribe|extortion|detain|custody|room|threat|violence|coercion|112)\b/.test(blob)
}

export interface UrgentContextClassification {
  direct_urgent: boolean
  category: string | null
  urgent_continuation: boolean
  emit_immediate_safety: boolean
  verification_guidance: string[]
}

export function classifyUrgentContext(
  message: string,
  memory?: Record<string, unknown> | null,
  priorSafetyMessages?: Array<Record<string, unknown>> | null
): UrgentContextClassification {
  const category = detectUrgentCategory(message)
  const alreadyWarned = Boolean(priorSafetyMessages && priorSafetyMessages.length > 0)
  const activePhysical = hasActivePhysicalUrgentCase(memory, priorSafetyMessages)
  const followup = Boolean(
    !category &&
      activePhysical &&
      !HYPOTHETICAL_RE.test((message || '').toLowerCase()) &&
      URGENT_FOLLOWUP_CUE_RE.test(message || '')
  )

  let guidance: string[] = []
  if (followup || category === 'physical_safety') {
    guidance = [
      'Do not confront or accuse suspected fake officers in person; move to a safe public/monitored area or stay with hotel management/trusted witnesses.',
      'Ask hotel reception/security immediately to preserve lobby/corridor CCTV footage, visitor register entries, and intercom logs with exact timestamps.',
      'Write down physical details while fresh: names used, uniform/badge markings, vehicle number, phone numbers, and any UPI ID/account or cash demand details.',
      'Verify whether any legitimate police team was dispatched by calling 112 (ERSS) or the local police control room from a safe phone.',
      'When speaking at a police station or control room, stay calm, ask for the Duty Officer or Station House Officer (SHO), state chronological facts you personally observed without speculating, and request a written acknowledgement or diary reference.',
    ]
  } else if (category === 'financial_cyber_fraud') {
    guidance = [
      "Call 1930 (India's National Cyber-Financial Fraud Helpline) immediately to report the unauthorized transactions and suspect details for fund-freeze coordination.",
      "Call your bank and wallet's official fraud helpline immediately to block compromised payment access and obtain a formal dispute/complaint reference number.",
      'From a clean, trusted device, reset wallet, banking, and email passwords/PINs, revoke active sessions, and remove any app installed via the suspicious link.',
      'File the complete complaint on https://cybercrime.gov.in preserving UTR/transaction IDs, bank SMS alerts, WhatsApp chat screenshots, scammer number, and phishing URL.',
    ]
  }

  return {
    direct_urgent: category !== null,
    category: category || (followup ? 'emergency_followup' : null),
    urgent_continuation: followup || (isPhysicalLibertyCategory(category) && alreadyWarned),
    emit_immediate_safety: category !== null && !alreadyWarned,
    verification_guidance: guidance,
  }
}

export function isContactVerified(
  contact: Pick<VerifiedContactRecord, 'checked_at' | 'revalidate_after' | 'retired'>,
  todayIso: string
): boolean {
  if (contact.retired) return false
  const current = todayIso.slice(0, 10)
  return contact.checked_at.slice(0, 10) <= current && current <= contact.revalidate_after.slice(0, 10)
}

export interface SafetyEventPayload {
  type: 'safety'
  category: string
  content_id: string
  text: string
  sources: string[]
  request_id?: string
}

export async function buildSafetyEvent(options: {
  language?: Language
  today?: string
  india?: boolean
  category?: string | null
  contacts?: Record<string, VerifiedContactRecord>
}): Promise<SafetyEventPayload> {
  const lang: Language = options.language && options.language in TEXT ? options.language : 'en'
  const normalized =
    !options.category || options.category === 'emergency' || options.category === 'emergency_followup'
      ? 'physical_safety'
      : options.category
  const currentIso = (options.today || new Date().toISOString()).slice(0, 10)
  const india = Boolean(options.india)
  const registry = { ...DEFAULT_VERIFIED_CONTACTS, ...(options.contacts || {}) }
  const sources: string[] = []

  if (normalized === 'financial_cyber_fraud') {
    let text = CYBER_FRAUD_TEXT[lang]
    const spec = registry.financial_cyber_fraud
    if (india && spec && isContactVerified(spec, currentIso)) {
      const extra: Record<Language, string> = {
        en: ' In India, call 1930 immediately (National Cyber-Financial Fraud Helpline) and report at cybercrime.gov.in with transaction IDs, phone numbers, and links.',
        hi: ' भारत में तुरंत 1930 (राष्ट्रीय साइबर-वित्तीय धोखाधड़ी हेल्पलाइन) पर कॉल करें और cybercrime.gov.in पर ट्रांज़ैक्शन ID, फोन नंबर व लिंक के साथ शिकायत दर्ज करें।',
        hinglish:
          ' India mein turant 1930 (National Cyber-Financial Fraud Helpline) par call karein aur cybercrime.gov.in par transaction IDs, phone numbers aur link ke saath report karein.',
      }
      text += extra[lang]
      sources.push(spec.official_source_url)
    }
    const hash = await sha256Hex(text)
    return {
      type: 'safety',
      category: 'financial_cyber_fraud',
      content_id: `safety-${hash.slice(0, 16)}`,
      text,
      sources,
    }
  }

  if (normalized === 'medical_emergency') {
    let text = MEDICAL_TEXT[lang]
    const spec = registry.medical_emergency
    if (india && spec && isContactVerified(spec, currentIso)) {
      const extra: Record<Language, string> = {
        en: ' In India, call 108 or 112 for an immediate ambulance/medical emergency.',
        hi: ' भारत में तत्काल एम्बुलेंस या चिकित्सा सहायता के लिए 108 या 112 पर कॉल करें।',
        hinglish: ' India mein immediate ambulance ya medical emergency ke liye 108 ya 112 par call karein.',
      }
      text += extra[lang]
      sources.push(spec.official_source_url)
    }
    const hash = await sha256Hex(text)
    return {
      type: 'safety',
      category: 'medical_emergency',
      content_id: `safety-${hash.slice(0, 16)}`,
      text,
      sources,
    }
  }

  let text = normalized === 'self_harm' ? SELF_HARM_TEXT[lang] : TEXT[lang]
  const contact112 = registry.physical_safety
  if (india && contact112 && isContactVerified(contact112, currentIso)) {
    const extra: Record<Language, string> = {
      en: ' In India, call 112 for an immediate emergency if it is safe to call.',
      hi: ' भारत में तत्काल आपात स्थिति में, कॉल करना सुरक्षित हो तो 112 पर कॉल करें।',
      hinglish: ' India mein immediate emergency ho aur call karna safe ho to 112 par call karein.',
    }
    text += extra[lang]
    sources.push(contact112.official_source_url)
  }

  if (india && (normalized === 'self_harm' || normalized === 'domestic_violence')) {
    const spec = registry[normalized]
    if (spec && isContactVerified(spec, currentIso)) {
      const specExtra: Record<Language, string> =
        normalized === 'self_harm'
          ? {
              en: ' For 24x7 mental-health crisis support in India, call Tele-MANAS at 14416.',
              hi: ' भारत में 24x7 मानसिक स्वास्थ्य सहायता के लिए Tele-MANAS के 14416 पर कॉल करें।',
              hinglish: ' India mein 24x7 mental-health crisis support ke liye Tele-MANAS par 14416 call karein.',
            }
          : {
              en: ' Women facing domestic violence or distress can also call the 181 Women Helpline if safe.',
              hi: ' घरेलू हिंसा या संकट की स्थिति में सुरक्षित होने पर 181 महिला हेल्पलाइन पर भी कॉल कर सकती हैं।',
              hinglish:
                ' Domestic violence ya distress mein safe hone par 181 Women Helpline par bhi call kar sakti hain.',
            }
      text += specExtra[lang]
      sources.push(spec.official_source_url)
    }
  }

  const hash = await sha256Hex(text)
  return {
    type: 'safety',
    category: normalized,
    content_id: `safety-${hash.slice(0, 16)}`,
    text,
    sources,
  }
}
