import { useState } from 'react'
import { Check, Globe, Sparkles, X } from 'lucide-react'
import type { Language } from '../types'

interface LanguageIntroModalProps {
  currentLanguage: Language
  onSelect: (lang: Language) => void
  onClose?: () => void
}

interface LanguageCardOption {
  id: Language
  label: string
  sublabel: string
  englishLabel: string
  scriptBadge: string
  tag?: string
}

const LANGUAGE_OPTIONS: LanguageCardOption[] = [
  {
    id: 'hi',
    label: 'हिन्दी',
    englishLabel: 'Hindi',
    sublabel: 'सरल भाषा में कानूनी अधिकार, सलाह और शिकायत ड्राफ्ट',
    scriptBadge: 'अ',
    tag: 'लोकप्रिय (Popular)',
  },
  {
    id: 'en',
    label: 'English',
    englishLabel: 'English',
    sublabel: 'Clear legal guidance, rights, and formal complaint drafting',
    scriptBadge: 'En',
  },
  {
    id: 'hinglish',
    label: 'Hinglish',
    englishLabel: 'Hinglish',
    sublabel: 'Aasan Hindi + English bolchaal: seedhi legal advice',
    scriptBadge: 'आ',
    tag: 'Conversational',
  },
]

export default function LanguageIntroModal({
  currentLanguage,
  onSelect,
  onClose,
}: LanguageIntroModalProps) {
  const [selected, setSelected] = useState<Language>(currentLanguage || 'hi')

  function handleConfirm() {
    onSelect(selected)
  }

  return (
    <div
      className="language-intro-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="language-intro-title"
    >
      <div className="language-intro-modal">
        {onClose && (
          <button
            type="button"
            className="lang-modal-close"
            onClick={onClose}
            aria-label="Close language selector"
          >
            <X size={18} />
          </button>
        )}

        <div className="lang-modal-header">
          <div className="lang-brand-badge">
            <Globe size={18} aria-hidden="true" />
            <span>Nyay Saathi • न्याय साथी</span>
          </div>
          <h1 id="language-intro-title">अपनी भाषा चुनें • Choose your language</h1>
          <p className="lang-modal-subtitle">
            आप बातचीत के दौरान कभी भी भाषा बदल सकते हैं।<br />
            <span>You can switch languages anytime during the conversation.</span>
          </p>
        </div>

        <div className="lang-cards-grid" role="radiogroup" aria-label="Preferred language">
          {LANGUAGE_OPTIONS.map((opt) => {
            const isSelected = selected === opt.id
            return (
              <button
                type="button"
                key={opt.id}
                role="radio"
                aria-checked={isSelected}
                className={`lang-card-item ${isSelected ? 'selected' : ''}`}
                onClick={() => setSelected(opt.id)}
                onDoubleClick={() => onSelect(opt.id)}
              >
                <div className="lang-card-top">
                  <span className="lang-card-badge">{opt.scriptBadge}</span>
                  {opt.tag && (
                    <span className="lang-card-tag">
                      <Sparkles size={11} aria-hidden="true" /> {opt.tag}
                    </span>
                  )}
                  {isSelected && (
                    <span className="lang-card-check" aria-hidden="true">
                      <Check size={14} />
                    </span>
                  )}
                </div>
                <div className="lang-card-body">
                  <div className="lang-card-names">
                    <strong className="lang-primary-name">{opt.label}</strong>
                    {opt.id !== 'en' && <span className="lang-secondary-name">({opt.englishLabel})</span>}
                  </div>
                  <p className="lang-card-desc">{opt.sublabel}</p>
                </div>
              </button>
            )
          })}
        </div>

        <div className="lang-modal-footer">
          <button
            type="button"
            className="lang-confirm-button"
            onClick={handleConfirm}
          >
            {selected === 'en'
              ? 'Continue with English →'
              : selected === 'hinglish'
              ? 'Hinglish mein shuru karein →'
              : 'हिन्दी में शुरू करें →'}
          </button>
        </div>
      </div>
    </div>
  )
}
