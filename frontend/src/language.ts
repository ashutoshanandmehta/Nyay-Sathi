import type { Language } from './types'
import { STARTER_ICONS } from './icons'

export interface WelcomeContent {
  badge: string
  headline: string
  description: string
  problemTitle: string
  problemSub: string
  voiceHeading: string
  placeholder: string
}

export const WELCOME_CONTENT: Record<Language, WelcomeContent> = {
  hi: {
    badge: 'नमस्ते! 😊',
    headline: 'बताइए, क्या हुआ?',
    description: 'अपनी बात खुलकर बताइए। हम आपकी परेशानी समझकर आगे का रास्ता सुझाएँगे।',
    problemTitle: 'कुछ आम परेशानियाँ',
    problemSub: 'क्या आपके साथ भी ऐसा हुआ है?',
    voiceHeading: 'बोलकर अपनी बात बताइए',
    placeholder: 'चाहें तो यहाँ लिखें…',
  },
  en: {
    badge: 'Hello! 😊',
    headline: 'What happened?',
    description: 'Share your situation openly. We will understand your issue and guide you on the right legal path.',
    problemTitle: 'Common Problems',
    problemSub: 'Has something like this happened to you?',
    voiceHeading: 'Hold to speak your issue',
    placeholder: 'Type your message or question here…',
  },
  hinglish: {
    badge: 'Namaste! 😊',
    headline: 'Bataiye, kya hua?',
    description: 'Apni baat khulkar bataiye. Hum aapki pareshani samajhkar aage ka legal rasta sujhayenge.',
    problemTitle: 'Kuch aam pareshaniyan',
    problemSub: 'Kya aapke saath bhi aisa hua hai?',
    voiceHeading: 'Bolkar apni baat bataiye',
    placeholder: 'Chahein toh yahan likhein…',
  },
}

export interface StarterCard {
  text: string
  hint: string
  icon: typeof STARTER_ICONS.refund.icon
}

export const STARTER_CARDS: Record<Language, StarterCard[]> = {
  hi: [
    {
      text: 'बैंक ने मेरे पैसे रोक रखे हैं',
      hint: '',
      icon: STARTER_ICONS.refund.icon,
    },
    {
      text: 'सामान लौटाया, पर पैसे वापस नहीं मिले',
      hint: '',
      icon: STARTER_ICONS.defective.icon,
    },
  ],
  en: [
    {
      text: 'The bank has held my money / blocked account',
      hint: '',
      icon: STARTER_ICONS.refund.icon,
    },
    {
      text: 'Returned goods, but refund not received',
      hint: '',
      icon: STARTER_ICONS.defective.icon,
    },
  ],
  hinglish: [
    {
      text: 'Bank ne mere paise hold kar rakhe hain',
      hint: '',
      icon: STARTER_ICONS.refund.icon,
    },
    {
      text: 'Saman return kiya, par refund nahi mila',
      hint: '',
      icon: STARTER_ICONS.defective.icon,
    },
  ],
}

// Unambiguous Hinglish marker tokens that do not collide with standard English words.
const HINGLISH_UNAMBIGUOUS = new Set([
  'hai', 'hain', 'hona', 'hoga', 'hogi', 'hoge', 'hua', 'hue', 'hui',
  'nahi', 'nahin', 'mat',
  'kya', 'kyu', 'kyun', 'kaise', 'kaha', 'kahan', 'kab', 'kisko', 'kisse', 'kaun',
  'kare', 'karein', 'karna', 'karne', 'karo', 'kiya', 'kiye',
  'diya', 'diye', 'dena', 'dene',
  'gaya', 'gaye', 'gayi', 'jana', 'jao', 'jaun',
  'paise', 'paisa', 'rupaye', 'rupay', 'kat', 'kate', 'katgaye', 'katwaye',
  'mera', 'meri', 'mere', 'mujhe', 'mujhko', 'mai', 'main',
  'hume', 'humko', 'hamara', 'hamari', 'hamare',
  'aap', 'aapka', 'aapke', 'aapki', 'aapne', 'aapko',
  'tum', 'tumhara', 'tumhe', 'tumko',
  'uska', 'uski', 'uske', 'usne', 'unka', 'unke', 'unki', 'unhone',
  'iska', 'iski', 'iske', 'isne', 'inke', 'inhe',
  'bataiye', 'batao', 'bataye', 'boliye', 'suno', 'dekho',
  'chahiye', 'mila', 'mile', 'mili', 'milna',
  'raha', 'rahe', 'rahi', 'tha', 'thi',
  'bhi', 'toh', 'lekin', 'magar',
  'baat', 'cheez', 'saman', 'khata', 'shikayat', 'thaney', 'thana',
  'abhi', 'pehle', 'baad', 'bheja', 'bhejo', 'wapas', 'laute', 'lautaya', 'rok', 'roka', 'rakha',
])

// English indicator words
const ENGLISH_WORDS = new Set([
  'the', 'is', 'are', 'was', 'were', 'has', 'have', 'had', 'and', 'or', 'to', 'in', 'on', 'at', 'by', 'for', 'with',
  'my', 'i', 'me', 'you', 'your', 'we', 'our', 'it', 'its', 'they', 'their', 'this', 'that', 'these', 'those',
  'refund', 'fraud', 'money', 'bank', 'account', 'returned', 'return', 'order', 'ordered', 'item', 'product',
  'seller', 'merchant', 'complaint', 'police', 'help', 'what', 'how', 'can', 'should', 'where', 'when', 'why', 'who',
  'deducted', 'payment', 'transaction', 'defective', 'court', 'legal', 'rights', 'please', 'withheld', 'weeks',
  'under', 'act', 'section', 'draft', 'consumer', 'commission', 'notice', 'reply', 'process', 'limitation', 'period',
  'cheated', 'delivery', 'delayed', 'damaged', 'compensation', 'lawyer', 'guidance', 'advice',
])

/**
 * Automatically detects whether the input string is in Hindi (Devanagari),
 * Hinglish (romanized Hindi), or English.
 * Returns null if the text is too short or ambiguous to determine.
 */
export function detectLanguage(text: string): Language | null {
  if (!text || text.trim().length < 2) return null
  const trimmed = text.trim()

  // 1. Devanagari script check (Hindi)
  const devanagariMatches = trimmed.match(/[\u0900-\u097F]/g)
  const devanagariCount = devanagariMatches ? devanagariMatches.length : 0
  if (devanagariCount >= 3 || (trimmed.length > 0 && devanagariCount / trimmed.length > 0.15)) {
    return 'hi'
  }

  // 2. Tokenize Latin script words
  const lower = trimmed.toLowerCase()
  const words = lower.match(/[a-z]+/g) || []
  if (words.length === 0) return null

  // 3. Hinglish tokens check
  let hinglishCount = 0
  for (const w of words) {
    if (HINGLISH_UNAMBIGUOUS.has(w)) hinglishCount++
  }

  if (hinglishCount >= 1) {
    return 'hinglish'
  }

  // 4. English tokens check
  let englishCount = 0
  for (const w of words) {
    if (ENGLISH_WORDS.has(w)) englishCount++
  }

  if (englishCount >= 1 && hinglishCount === 0) {
    return 'en'
  }

  return null
}
