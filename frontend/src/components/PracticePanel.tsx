import { ArrowLeft, ArrowUp, ArrowRight, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Language, RoleplayChatMessage, RoleplaySetup } from '../types'

export default function PracticePanel({
  caseId,
  language = 'en',
  onClose,
  setupDelayMs = 3400,
}: {
  caseId: string
  language?: Language
  onClose?: () => void
  setupDelayMs?: number
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [setupData, setSetupData] = useState<RoleplaySetup | null>(null)
  const [selectedStakeholder, setSelectedStakeholder] = useState<string>('')
  const [customStakeholder, setCustomStakeholder] = useState<string>('')

  // 3-4 second setup transition state
  const [isSettingUp, setIsSettingUp] = useState(false)
  const [setupStepText, setSetupStepText] = useState('')

  // Active chat session state
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [activeStakeholder, setActiveStakeholder] = useState<string>('')
  const [messages, setMessages] = useState<RoleplayChatMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const chatBottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadSetup()
  }, [caseId])

  useEffect(() => {
    if (sessionId) {
      chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length, sessionId])

  async function loadSetup() {
    setLoading(true)
    setError('')
    try {
      const data = await api.roleplaySetup(caseId)
      setSetupData(data)
      if (data.stakeholders.length > 0) {
        setSelectedStakeholder(data.stakeholders[0])
      } else {
        setSelectedStakeholder('Police officer')
      }
    } catch (e) {
      setError((e as Error).message || 'Failed to load case context for roleplay.')
    } finally {
      setLoading(false)
    }
  }

  async function startRoleplay() {
    if (!selectedStakeholder) return
    setError('')
    setIsSettingUp(true)

    const targetStakeholder =
      selectedStakeholder === 'Someone else'
        ? (customStakeholder.trim() || 'Opposing party')
        : selectedStakeholder

    setSetupStepText(`Setting up ${targetStakeholder} persona...`)

    const delay = setupDelayMs
    const t1 = setTimeout(() => {
      setSetupStepText('Loading your case context...')
    }, Math.min(delay * 0.4, 1400))
    const t2 = setTimeout(() => {
      setSetupStepText('Starting roleplay simulation...')
    }, Math.min(delay * 0.8, 2800))

    try {
      const res = await api.roleplayStart(
        caseId,
        selectedStakeholder,
        selectedStakeholder === 'Someone else' ? customStakeholder.trim() : undefined,
        language
      )
      setTimeout(() => {
        setSessionId(res.session_id)
        setActiveStakeholder(res.stakeholder)
        setMessages([
          {
            id: 'm-0',
            role: 'opponent',
            text: res.opening_message,
          },
        ])
        setIsSettingUp(false)
      }, delay)
    } catch (e) {
      clearTimeout(t1)
      clearTimeout(t2)
      setIsSettingUp(false)
      setError((e as Error).message || 'Could not start roleplay session.')
    }
  }

  async function sendMessage(e?: React.FormEvent) {
    if (e) e.preventDefault()
    if (!sessionId || !inputText.trim() || sending) return
    const textToSend = inputText.trim()
    setInputText('')
    setSending(true)
    setError('')

    const userMsg: RoleplayChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      text: textToSend,
    }
    setMessages(prev => [...prev, userMsg])

    try {
      const res = await api.roleplayChat(caseId, sessionId, textToSend, language)
      const opponentMsg: RoleplayChatMessage = {
        id: `o-${Date.now()}`,
        role: 'opponent',
        text: res.reply,
      }
      setMessages(prev => [...prev, opponentMsg])
    } catch (err) {
      setError((err as Error).message || 'Response error.')
    } finally {
      setSending(false)
    }
  }

  function endPractice() {
    setSessionId(null)
    setActiveStakeholder('')
    setMessages([])
    onClose?.()
  }

  // 1. LOADING STATE
  if (loading && !setupData) {
    return (
      <div className="roleplay-drawer-container">
        <div className="roleplay-loading-wrap">
          <div className="roleplay-spinner" />
          <p>Analyzing case background...</p>
        </div>
      </div>
    )
  }

  // 2. 3-4 SECOND SETUP TRANSITION SCREEN
  if (isSettingUp) {
    return (
      <div className="roleplay-drawer-container">
        <div className="roleplay-setup-transition">
          <div className="roleplay-spinner-large" />
          <h4>Preparing Roleplay</h4>
          <p className="roleplay-transition-status">{setupStepText}</p>
        </div>
      </div>
    )
  }

  // 3. ACTIVE CONVERSATIONAL CHAT SCREEN (Matches Reference 2)
  if (sessionId) {
    return (
      <div className="roleplay-drawer-container active-chat-mode">
        {/* Header */}
        <div className="roleplay-chat-header">
          <div className="roleplay-header-titles">
            <h3 className="roleplay-stakeholder-name">{activeStakeholder}</h3>
            <span className="roleplay-subtitle">Practice simulation</span>
          </div>
          <button type="button" className="roleplay-end-btn" onClick={endPractice}>
            End practice
          </button>
        </div>

        {error && <div className="roleplay-inline-error">{error}</div>}

        {/* Message Stream */}
        <div className="roleplay-messages-scroll">
          {messages.map(m => (
            <div key={m.id} className={`roleplay-message-row ${m.role}`}>
              {m.role === 'opponent' ? (
                <div className="roleplay-opponent-bubble">{m.text}</div>
              ) : (
                <div className="roleplay-user-bubble">{m.text}</div>
              )}
            </div>
          ))}
          {sending && (
            <div className="roleplay-message-row opponent">
              <div className="roleplay-typing-dots">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={chatBottomRef} />
        </div>

        {/* Composer */}
        <div className="roleplay-composer-bottom">
          <form onSubmit={sendMessage} className="roleplay-composer-form">
            <input
              type="text"
              aria-label="Type your response"
              placeholder="Type your response..."
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              disabled={sending}
              autoFocus
            />
            <button
              type="submit"
              disabled={!inputText.trim() || sending}
              className="roleplay-send-btn"
              aria-label="Send response"
            >
              <ArrowUp size={16} />
            </button>
          </form>
        </div>
      </div>
    )
  }

  // 4. SETUP & STAKEHOLDER SELECTION SCREEN (Matches Reference 1)
  const stakeholdersList = [
    ...(setupData?.stakeholders || ['Police officer', 'Opposing lawyer']),
    'Someone else',
  ]

  return (
    <div className="roleplay-drawer-container">
      {/* Top Title Bar */}
      <div className="roleplay-setup-top">
        <button type="button" className="roleplay-back-link" onClick={onClose}>
          <ArrowLeft size={16} /> Practice Arena
        </button>
      </div>

      <div className="roleplay-setup-content">
        <h2 className="roleplay-main-heading">Practice your conversation</h2>
        <p className="roleplay-main-subheading">Prepare for what the other side might say.</p>

        {error && <div className="roleplay-inline-error">{error}</div>}

        {/* Based on your case card */}
        <div className="roleplay-case-box">
          <span className="roleplay-case-tag">BASED ON YOUR CASE</span>
          <h4 className="roleplay-case-title">{setupData?.case_title || 'Your Case'}</h4>
          <p className="roleplay-case-desc">
            {setupData?.case_synopsis || 'Incident details recorded from your conversation.'}
          </p>
        </div>

        {/* Radio List */}
        <div className="roleplay-stakeholders-section">
          <label className="roleplay-question-label">Who do you want to practice with?</label>
          <div className="roleplay-radios-list" role="radiogroup">
            {stakeholdersList.map(st => {
              const isSelected = selectedStakeholder === st
              return (
                <div
                  key={st}
                  className="roleplay-radio-row"
                  onClick={() => setSelectedStakeholder(st)}
                >
                  <div className={`roleplay-radio-circle ${isSelected ? 'selected' : ''}`}>
                    {isSelected && <div className="roleplay-radio-inner" />}
                  </div>
                  <span className="roleplay-radio-text">{st}</span>
                </div>
              )
            })}
          </div>

          {selectedStakeholder === 'Someone else' && (
            <div className="roleplay-custom-input-wrap">
              <input
                type="text"
                placeholder="e.g. Income Tax Officer, Landlord, Grievance Officer..."
                value={customStakeholder}
                onChange={e => setCustomStakeholder(e.target.value)}
                autoFocus
              />
            </div>
          )}
        </div>

        {/* Start Button */}
        <div className="roleplay-action-wrap">
          <button
            type="button"
            className="roleplay-start-btn"
            onClick={startRoleplay}
            disabled={selectedStakeholder === 'Someone else' && !customStakeholder.trim()}
          >
            Start Practice <ArrowRight size={17} />
          </button>
        </div>
      </div>
    </div>
  )
}
