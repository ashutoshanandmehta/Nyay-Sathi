import { describe, expect, it } from 'vitest'
import { detectLanguage } from './language'

describe('language auto-detection', () => {
  it('detects Hindi in Devanagari script', () => {
    expect(detectLanguage('बैंक ने मेरे पैसे रोक रखे हैं')).toBe('hi')
    expect(detectLanguage('सामान लौटाया, पर पैसे वापस नहीं मिले')).toBe('hi')
    expect(detectLanguage('उपभोक्ता फोरम में केस कैसे दर्ज करें?')).toBe('hi')
  })

  it('detects Hinglish in Latin script', () => {
    expect(detectLanguage('Maine 3 hafte pehle earphones return kiye the, abhi tak refund nahi mila')).toBe('hinglish')
    expect(detectLanguage('Bank se unauthorised transaction hua hai, kya karun?')).toBe('hinglish')
    expect(detectLanguage('Cyber crime portal par complaint kaise register karein?')).toBe('hinglish')
    expect(detectLanguage('Mera paisa account se kat gaya')).toBe('hinglish')
    expect(detectLanguage('Police station me FIR darj nahi kar rahe hain')).toBe('hinglish')
  })

  it('detects English queries', () => {
    expect(detectLanguage('The bank has withheld my ₹2,800 refund for three weeks')).toBe('en')
    expect(detectLanguage('Please help me draft a consumer court complaint')).toBe('en')
    expect(detectLanguage('What is the limitation period under Consumer Protection Act?')).toBe('en')
    expect(detectLanguage('Can you write a complaint email to the seller?')).toBe('en')
    expect(detectLanguage('My credit card was charged twice for the same transaction')).toBe('en')
  })

  it('returns null for ambiguous or ultra-short input', () => {
    expect(detectLanguage('')).toBeNull()
    expect(detectLanguage('ok')).toBeNull()
    expect(detectLanguage('12345')).toBeNull()
  })
})

describe('Language intro selection options', () => {
  it('provides localized content and starter cards for all three languages', async () => {
    const { WELCOME_CONTENT, STARTER_CARDS } = await import('./language')
    for (const lang of ['hi', 'en', 'hinglish'] as const) {
      expect(WELCOME_CONTENT[lang].headline).toBeTruthy()
      expect(WELCOME_CONTENT[lang].problemTitle).toBeTruthy()
      expect(STARTER_CARDS[lang].length).toBeGreaterThanOrEqual(2)
      expect(STARTER_CARDS[lang][0].text).toBeTruthy()
    }
  })
})
