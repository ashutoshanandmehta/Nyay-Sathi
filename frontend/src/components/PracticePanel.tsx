import { AlertTriangle, ArrowRight, Award, CheckCircle2, ChevronDown, ChevronUp, Copy, HelpCircle, MessageSquare, Mic, MicOff, RotateCcw, Send, ShieldAlert, Sparkles, Swords, User, Volume2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { CoachFeedback, Detail, Language, PracticeScenario, PracticeSession, PracticeTurn } from '../types'

export default function PracticePanel({
  caseId,
  language = 'en',
  onRefreshCase,
}: {
  caseId: string
  language?: Language
  onRefreshCase?: () => void
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [scenarios, setScenarios] = useState<PracticeScenario[]>([])
  const [activeSession, setActiveSession] = useState<PracticeSession | null>(null)
  const [pastSessions, setPastSessions] = useState<PracticeSession[]>([])
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('')
  const [customPrompt, setCustomPrompt] = useState('')
  const [showCustom, setShowCustom] = useState(false)

  // Turn submission state
  const [argumentText, setArgumentText] = useState('')
  const [submittingTurn, setSubmittingTurn] = useState(false)
  const [expandedCoachIdx, setExpandedCoachIdx] = useState<number | null>(null)
  const [exportedStatus, setExportedStatus] = useState('')
  const [recording, setRecording] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const threadBottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadScenariosAndSessions()
  }, [caseId])

  useEffect(() => {
    if (activeSession) {
      threadBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      if (activeSession.turns.length > 0) {
        setExpandedCoachIdx(activeSession.turns.length - 1)
      }
    }
  }, [activeSession?.turns.length])

  async function loadScenariosAndSessions() {
    setLoading(true)
    setError('')
    try {
      const [scList, sessList] = await Promise.all([
        api.practiceScenarios(caseId),
        api.listPracticeSessions(caseId),
      ])
      setScenarios(scList)
      setPastSessions(sessList)
      if (scList.length > 0 && !selectedScenarioId) {
        setSelectedScenarioId(scList[0].scenario_id)
      }
    } catch (e) {
      setError((e as Error).message || 'Failed to load practice scenarios.')
    } finally {
      setLoading(false)
    }
  }

  async function startSession(scId: string) {
    setLoading(true)
    setError('')
    try {
      const payload: { scenario_id: string; custom_scenario?: string; language?: Language } = {
        scenario_id: scId,
        language,
      }
      if (scId === 'custom' && customPrompt.trim()) {
        payload.custom_scenario = customPrompt.trim()
      }
      const session = await api.startPracticeSession(caseId, payload)
      setActiveSession(session)
      setExportedStatus('')
      setArgumentText('')
    } catch (e) {
      setError((e as Error).message || 'Could not start practice session.')
    } finally {
      setLoading(false)
    }
  }

  async function resumeSession(sessionId: string) {
    setLoading(true)
    setError('')
    try {
      const session = await api.getPracticeSession(caseId, sessionId)
      setActiveSession(session)
      setExportedStatus('')
    } catch (e) {
      setError((e as Error).message || 'Could not load practice session.')
    } finally {
      setLoading(false)
    }
  }

  async function submitTurn(e?: React.FormEvent) {
    if (e) e.preventDefault()
    if (!activeSession || !argumentText.trim() || submittingTurn) return
    const textToSend = argumentText.trim()
    setSubmittingTurn(true)
    setError('')
    try {
      const turn = await api.practiceTurn(caseId, activeSession.id, textToSend, language)
      setActiveSession(prev => {
        if (!prev) return null
        return {
          ...prev,
          turns: [...prev.turns, turn],
        }
      })
      setArgumentText('')
    } catch (err) {
      setError((err as Error).message || 'Failed to evaluate turn.')
    } finally {
      setSubmittingTurn(false)
    }
  }

  async function savePointsToCase() {
    if (!activeSession || activeSession.turns.length === 0) return
    setLoading(true)
    try {
      // Collect suggested phrasings and statutory safeguards as action items
      const actions: string[] = []
      activeSession.turns.forEach(t => {
        if (t.coach_feedback.suggested_phrasing) {
          actions.push(`Assert key defense: ${t.coach_feedback.suggested_phrasing.slice(0, 100)}...`)
        }
        t.coach_feedback.statutory_safeguards.forEach(s => {
          actions.push(`Cite ${s.act} ${s.section} (${s.title})`)
        })
      })
      const uniqueActions = Array.from(new Set(actions)).slice(0, 4)
      const res = await api.exportPracticeActions(caseId, activeSession.id, uniqueActions)
      setExportedStatus(`Saved ${res.exported_count} key arguments to Your case action tracker!`)
      onRefreshCase?.()
    } catch (e) {
      setError((e as Error).message || 'Could not save actions to case.')
    } finally {
      setLoading(false)
    }
  }

  // Voice recording
  async function toggleRecording() {
    if (recording) {
      mediaRecorderRef.current?.stop()
      setRecording(false)
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const recorder = new MediaRecorder(stream)
        audioChunksRef.current = []
        recorder.ondataavailable = e => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data)
        }
        recorder.onstop = async () => {
          const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
          const file = new File([blob], 'recording.webm', { type: 'audio/webm' })
          try {
            const res = await api.transcribe(file)
            if (res.transcript) {
              setArgumentText(prev => (prev ? `${prev} ${res.transcript}` : res.transcript))
            }
          } catch {
            setError('Audio transcription failed. You can type your argument directly.')
          }
        }
        mediaRecorderRef.current = recorder
        recorder.start()
        setRecording(true)
      } catch {
        setError('Microphone access denied or unsupported.')
      }
    }
  }

  if (loading && !activeSession) {
    return (
      <div className="panel-content practice-arena">
        <div className="practice-loading">
          <Swords className="spin-icon" size={24} />
          <p>Preparing legal practice scenarios from your case...</p>
        </div>
      </div>
    )
  }

  // SCENARIO PICKER VIEW
  if (!activeSession) {
    return (
      <div className="panel-content practice-arena">
        <div className="practice-header-hero">
          <div className="practice-hero-tag">
            <Swords size={15} />
            <span>Argument Practice Arena</span>
          </div>
          <h3>Simulate the Other Side & Practice Counter-Arguments</h3>
          <p className="muted">
            Face tough questioning from police, company officers, landlords, or opposing counsel.
            Test your arguments safely before walking into real meetings or courtrooms.
          </p>
        </div>

        {error && <div className="practice-error-banner" role="alert">{error}</div>}

        <div className="practice-scenarios-section">
          <h4>Case-Tailored Scenarios</h4>
          <div className="scenario-cards-list">
            {scenarios.map(sc => {
              const selected = selectedScenarioId === sc.scenario_id
              return (
                <div
                  key={sc.scenario_id}
                  className={`scenario-card ${selected ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedScenarioId(sc.scenario_id)
                    setShowCustom(false)
                  }}
                >
                  <div className="scenario-card-top">
                    <span className="scenario-domain-pill">{sc.domain.toUpperCase()}</span>
                    <span className="scenario-role-badge">Opponent: {sc.opponent_role}</span>
                  </div>
                  <h5>{sc.title}</h5>
                  <p className="scenario-desc"><strong>Setting:</strong> {sc.setting}</p>
                  <p className="scenario-objective"><strong>Your Goal:</strong> {sc.objective}</p>
                  <div className="scenario-opening-preview">
                    <small className="muted">Opponent opening line:</small>
                    <blockquote>"{sc.opening_statement}"</blockquote>
                  </div>
                  {selected && (
                    <button
                      type="button"
                      className="start-drill-btn"
                      onClick={e => {
                        e.stopPropagation()
                        startSession(sc.scenario_id)
                      }}
                    >
                      Start This Practice Drill <ArrowRight size={15} />
                    </button>
                  )}
                </div>
              )
            })}

            {/* Custom Scenario Card */}
            <div
              className={`scenario-card custom-scenario-card ${showCustom ? 'selected' : ''}`}
              onClick={() => {
                setShowCustom(true)
                setSelectedScenarioId('custom')
              }}
            >
              <div className="scenario-card-top">
                <span className="scenario-domain-pill">CUSTOM</span>
                <span className="scenario-role-badge">Opponent: You Choose</span>
              </div>
              <h5>Custom Dispute Scenario</h5>
              <p className="scenario-desc">Practice for a specific conversation, authority, or challenge.</p>
              {showCustom && (
                <div className="custom-input-wrap" onClick={e => e.stopPropagation()}>
                  <textarea
                    placeholder="e.g. My landlord is refusing to return my security deposit saying painting costs ₹35,000..."
                    value={customPrompt}
                    onChange={e => setCustomPrompt(e.target.value)}
                    rows={3}
                  />
                  <button
                    type="button"
                    disabled={!customPrompt.trim()}
                    className="start-drill-btn"
                    onClick={() => startSession('custom')}
                  >
                    Start Custom Drill <ArrowRight size={15} />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {pastSessions.length > 0 && (
          <div className="past-sessions-section">
            <h4>Past Practice Drills ({pastSessions.length})</h4>
            <div className="past-sessions-list">
              {pastSessions.map(ps => (
                <div key={ps.id} className="past-session-item">
                  <div>
                    <strong>{ps.title}</strong>
                    <div className="past-session-meta">
                      <span>{ps.opponent_role}</span> · <span>{ps.turn_count || 0} rounds</span> · <span>{ps.status}</span>
                    </div>
                  </div>
                  <button type="button" onClick={() => resumeSession(ps.id)}>
                    View / Resume
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // ACTIVE DRILL ARENA VIEW
  const roundCount = activeSession.turns.length
  const currentScenario =
    scenarios.find(s => s.scenario_id === activeSession.scenario_id) || {
      title: activeSession.title,
      opponent_role: activeSession.opponent_role,
      setting: activeSession.setting,
      objective: activeSession.objective,
      suggested_first_response: null,
    }

  return (
    <div className="panel-content practice-arena-active">
      {/* Top Session Bar */}
      <div className="practice-active-header">
        <div className="practice-header-meta">
          <button
            type="button"
            className="practice-back-btn"
            onClick={() => {
              setActiveSession(null)
              loadScenariosAndSessions()
            }}
          >
            ← Switch Scenario
          </button>
          <span className="hypothetical-watermark-pill">
            Simulated Opposition · Strictly Hypothetical
          </span>
        </div>
        <h4>{activeSession.title}</h4>
        <div className="active-details-row">
          <span><strong>Opponent:</strong> {activeSession.opponent_role}</span>
          <span><strong>Location:</strong> {activeSession.setting}</span>
          <span className="practice-round-pill">Round {roundCount + 1} of 4</span>
        </div>
        <div className="active-goal-box">
          <Award size={14} />
          <span><strong>Objective:</strong> {activeSession.objective}</span>
        </div>
      </div>

      {error && <div className="practice-error-banner" role="alert">{error}</div>}
      {exportedStatus && <div className="practice-success-banner" role="status">{exportedStatus}</div>}

      {/* Discussion Thread */}
      <div className="practice-thread-scroll">
        {/* Opening Opponent Challenge */}
        <div className="practice-bubble opponent-bubble opening-turn">
          <div className="bubble-header">
            <span className="opponent-title-chip">
              <Swords size={13} /> {activeSession.opponent_role}
            </span>
            <small className="turn-label">Initial Challenge</small>
          </div>
          <p className="bubble-content">{activeSession.opening_statement}</p>
        </div>

        {/* Turn History */}
        {activeSession.turns.map((turn, idx) => {
          const isExpanded = expandedCoachIdx === idx
          const fb = turn.coach_feedback
          return (
            <div key={turn.id || idx} className="practice-turn-block">
              {/* User Argument Bubble */}
              <div className="practice-bubble user-bubble">
                <div className="bubble-header">
                  <span className="user-title-chip"><User size={13} /> Your Argument</span>
                  <small className="turn-label">Round {turn.turn_index}</small>
                </div>
                <p className="bubble-content">{turn.user_argument}</p>
              </div>

              {/* Coach Evaluation Card */}
              <div className={`practice-coach-card assessment-${fb.assessment}`}>
                <div
                  className="coach-card-header"
                  onClick={() => setExpandedCoachIdx(isExpanded ? null : idx)}
                >
                  <div className="coach-header-left">
                    <Sparkles size={16} />
                    <strong>Defense Coach Analysis</strong>
                    <span className={`assessment-badge badge-${fb.assessment}`}>
                      {fb.assessment === 'strong' ? '🟢 Solid Position' : fb.assessment === 'caution' ? '🟡 Caution Needed' : '🔴 Risky Admission'}
                    </span>
                  </div>
                  <button type="button" className="coach-toggle-btn" aria-label="Toggle analysis">
                    {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>

                {isExpanded && (
                  <div className="coach-card-body">
                    {fb.is_crisis && (
                      <div className="crisis-alert-box" role="alert">
                        <ShieldAlert size={16} />
                        <div>
                          <strong>Emergency Protocol:</strong>
                          <p>{fb.crisis_text}</p>
                        </div>
                      </div>
                    )}

                    {fb.anti_fabrication_warning && (
                      <div className="fabrication-warning-box">
                        <AlertTriangle size={15} />
                        <span>{fb.anti_fabrication_warning}</span>
                      </div>
                    )}

                    {fb.strengths.length > 0 && (
                      <div className="coach-points-section">
                        <h6>Effective Points Made:</h6>
                        <ul>
                          {fb.strengths.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {fb.vulnerabilities.length > 0 && (
                      <div className="coach-points-section vulnerabilities-section">
                        <h6>Risks & Traps to Avoid:</h6>
                        <ul>
                          {fb.vulnerabilities.map((v, i) => (
                            <li key={i}>{v}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {fb.statutory_safeguards.length > 0 && (
                      <div className="coach-safeguards-section">
                        <h6>Statutory Grounds You Can Assert:</h6>
                        {fb.statutory_safeguards.map((safeguard, i) => (
                          <div key={i} className="safeguard-item">
                            <b>{safeguard.act} — {safeguard.section}: {safeguard.title}</b>
                            <p>{safeguard.relevance}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {fb.suggested_phrasing && (
                      <div className="coach-suggested-box">
                        <div className="suggested-header">
                          <h6>Truthful Suggested Phrasing:</h6>
                          <button
                            type="button"
                            onClick={() => setArgumentText(fb.suggested_phrasing)}
                            title="Copy to composer"
                          >
                            <Copy size={13} /> Use this phrasing
                          </button>
                        </div>
                        <p>"{fb.suggested_phrasing}"</p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Opponent Reply */}
              <div className="practice-bubble opponent-bubble">
                <div className="bubble-header">
                  <span className="opponent-title-chip">
                    <Swords size={13} /> {activeSession.opponent_role}
                  </span>
                  <small className="turn-label">Counter-Challenge</small>
                </div>
                <p className="bubble-content">{turn.opponent_reply}</p>
              </div>
            </div>
          )
        })}

        {/* Readiness Wrap-Up Card when rounds reach 3+ */}
        {roundCount >= 3 && (
          <div className="practice-scorecard-card">
            <div className="scorecard-head">
              <Award size={18} />
              <div>
                <h5>Drill Milestones Completed</h5>
                <p className="muted">You have successfully practiced the primary arguments and counter-points.</p>
              </div>
            </div>
            <div className="scorecard-actions">
              <button
                type="button"
                className="save-actions-btn"
                disabled={loading}
                onClick={savePointsToCase}
              >
                <CheckCircle2 size={15} /> Save Key Points to Your Case Actions
              </button>
            </div>
          </div>
        )}

        <div ref={threadBottomRef} />
      </div>

      {/* Argument Composer */}
      <div className="practice-composer-wrapper">
        <form onSubmit={submitTurn} className="practice-composer-form">
          <textarea
            aria-label="Your counter-argument"
            placeholder={
              roundCount === 0 && currentScenario.suggested_first_response
                ? `e.g. "${currentScenario.suggested_first_response.slice(0, 100)}..."`
                : "Type your argument or defense response to the opponent..."
            }
            value={argumentText}
            onChange={e => setArgumentText(e.target.value)}
            rows={2}
            disabled={submittingTurn}
          />
          <div className="practice-composer-actions">
            <button
              type="button"
              className={`mic-btn ${recording ? 'recording' : ''}`}
              onClick={toggleRecording}
              title={recording ? 'Stop recording' : 'Speak your argument'}
              aria-label={recording ? 'Stop recording' : 'Speak your argument'}
            >
              {recording ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
            {roundCount === 0 && currentScenario.suggested_first_response && (
              <button
                type="button"
                className="help-hint-btn"
                onClick={() => setArgumentText(currentScenario.suggested_first_response || '')}
              >
                <HelpCircle size={14} /> Suggest First Response
              </button>
            )}
            <button
              type="submit"
              disabled={submittingTurn || !argumentText.trim()}
              className="send-arg-btn"
            >
              {submittingTurn ? 'Analyzing…' : <><Send size={15} /> Argue</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
