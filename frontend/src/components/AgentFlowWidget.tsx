import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Layers,
  RotateCw,
  Scale,
  Search,
  Sparkles,
  Terminal,
  Wrench,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { StreamEvent } from '../types'

export type AgentStageId = 'context' | 'reasoning' | 'research' | 'verifier' | 'repair' | 'final'

export interface AgentFlowWidgetProps {
  isStreaming: boolean
  events: StreamEvent[]
  activeStage?: string
  onOpenWorkflow?: () => void
}

interface StageDefinition {
  id: AgentStageId
  label: string
  agentName: string
  sublabel: string
  icon: typeof Sparkles
  color: string
}

const STAGES: StageDefinition[] = [
  {
    id: 'context',
    label: 'Context & Intake',
    agentName: 'Context & Intake Agent',
    sublabel: 'Facts & certified legal provisions',
    icon: Layers,
    color: '#0284c7', // Sky
  },
  {
    id: 'reasoning',
    label: 'Primary Reasoning',
    agentName: 'Primary Reasoning Agent',
    sublabel: 'Synthesizing response & legal claims',
    icon: Cpu,
    color: '#2563eb', // Indigo
  },
  {
    id: 'research',
    label: 'Legal Retrieval',
    agentName: 'Legal Retrieval Agent',
    sublabel: 'Statutory corpus & official portals',
    icon: Search,
    color: '#d97706', // Amber
  },
  {
    id: 'verifier',
    label: 'Verifier Agent',
    agentName: 'Verifier Agent',
    sublabel: 'Independent grounding & safety audit',
    icon: Scale,
    color: '#7c3aed', // Purple
  },
  {
    id: 'repair',
    label: 'Feedback Loop',
    agentName: 'Feedback Repair Loop',
    sublabel: 'Verifier flagged repair → Self-healing',
    icon: RotateCw,
    color: '#ea580c', // Orange
  },
  {
    id: 'final',
    label: 'Certified Output',
    agentName: 'Output Structuring & Certification Agent',
    sublabel: 'Verified & certified for publication',
    icon: CheckCircle2,
    color: '#16a34a', // Emerald
  },
]

export default function AgentFlowWidget({
  isStreaming,
  events,
  onOpenWorkflow,
}: AgentFlowWidgetProps) {
  const [visible, setVisible] = useState(isStreaming)
  const [showTrace, setShowTrace] = useState(false)
  const traceEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isStreaming) {
      setVisible(true)
    } else {
      // Disappear smoothly after response is delivered
      const timer = setTimeout(() => {
        setVisible(false)
        setShowTrace(false)
      }, 1200)
      return () => clearTimeout(timer)
    }
  }, [isStreaming])

  // Auto-scroll trace log when new events arrive
  useEffect(() => {
    if (showTrace && traceEndRef.current) {
      traceEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, showTrace])

  // Map incoming raw stage strings to our 6 stages
  const activeStageId = useMemo<AgentStageId>(() => {
    if (!events.length) return 'context'
    const last = events[events.length - 1]
    const s = last.stage?.toLowerCase() || ''
    if (s === 'saving' || s === 'context' || s === 'triage' || s === 'intake' || s === 'checks') {
      return 'context'
    }
    if (s === 'primary' || s === 'reasoning' || s === 'model_call' || s === 'respond' || s === 'plan_resolution') {
      return 'reasoning'
    }
    if (s === 'web_research' || s === 'research' || s === 'web_search' || s === 'web_fetch') {
      return 'research'
    }
    if (s === 'review' || s === 'assess_information') {
      return 'verifier'
    }
    if (s === 'revision' || s === 'repair' || s === 'fix' || s === 'revise') {
      return 'repair'
    }
    if (s === 'verify' || s === 'complete' || s === 'result' || s === 'compose' || s === 'structuring') {
      return 'final'
    }
    return 'reasoning'
  }, [events])

  const stageIndex = STAGES.findIndex(s => s.id === activeStageId)
  const activeStage = STAGES[stageIndex >= 0 ? stageIndex : 0]
  const isLoop = activeStage.id === 'repair'
  const isFinal = activeStage.id === 'final'
  const Icon = activeStage.icon

  // Last event details for comprehensive transparency
  const lastEvent = events[events.length - 1]
  const activeAgent = lastEvent?.agent || activeStage.agentName
  const activeTool = lastEvent?.tool
  const fetchedResult = lastEvent?.result || (lastEvent?.passages_count ? `Loaded ${lastEvent.passages_count} legal provisions` : null)
  const whatWentWrong = lastEvent?.warning || lastEvent?.error || (isLoop ? 'Verifier flagged ungrounded claim → Self-healing feedback loop' : null)
  const currentAction = lastEvent?.action || lastEvent?.detail || activeStage.sublabel

  // Disappear when not streaming and no active visible turn
  if (!visible) return null

  return (
    <div
      className={`flowing-widget ${isLoop ? 'loop-active' : ''} ${showTrace ? 'expanded' : ''}`}
      role="status"
      aria-label="Flowinggg"
    >
      {/* Flowinggg Header */}
      <div className="flowing-header">
        <div className="flowing-brand">
          <span className="flowing-pulse-dot" />
          <span className="flowing-title">Flowinggg</span>
        </div>
        <div className="flowing-meta">
          <button
            type="button"
            className="flowing-trace-toggle-btn"
            onClick={() => setShowTrace(prev => !prev)}
            title="Toggle live execution trace and tool results"
          >
            <Terminal size={11} />
            <span>Trace ({events.length})</span>
            {showTrace ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
          <span className="flowing-step-pill">{stageIndex + 1}/6</span>
          {onOpenWorkflow && (
            <button
              type="button"
              className="flowing-workflow-link"
              onClick={onOpenWorkflow}
              title="Inspect complete Agent Workflow"
            >
              Workflow
            </button>
          )}
        </div>
      </div>

      {/* Main Single Active Card */}
      <div className="flowing-card" key={activeStage.id}>
        <div
          className="flowing-icon-wrap"
          style={{
            borderColor: activeStage.color,
            color: activeStage.color,
          }}
        >
          <Icon size={16} className={isLoop ? 'spin-loop' : 'flowing-icon-breathing'} />
        </div>

        <div className="flowing-info">
          <div className="flowing-stage-name-row">
            <span className="flowing-stage-name">{activeStage.label}</span>
            {activeAgent && activeAgent !== activeStage.label && (
              <span className="flowing-agent-pill" title={`Active Agent: ${activeAgent}`}>
                {activeAgent.replace(' Agent', '')}
              </span>
            )}
            <span
              className="flowing-status-badge"
              style={{
                background: `${activeStage.color}15`,
                color: activeStage.color,
                borderColor: `${activeStage.color}30`,
              }}
            >
              {isLoop ? 'Loop active' : isFinal ? 'Certified' : 'Working'}
            </span>
          </div>

          {/* Tool Pill if tool was called */}
          {activeTool && (
            <div className="flowing-tool-pill">
              <Wrench size={10} />
              <span>Tool: <b>{activeTool}</b></span>
            </div>
          )}

          {/* Current action / detail */}
          <p className="flowing-detail-text">{currentAction}</p>

          {/* Fetched Result Banner */}
          {fetchedResult && (
            <div className="flowing-result-pill">
              <span>📥 {fetchedResult}</span>
            </div>
          )}

          {/* What Went Wrong / Warning Banner */}
          {whatWentWrong && (
            <div className="flowing-warning-pill">
              <AlertTriangle size={11} />
              <span>{whatWentWrong}</span>
            </div>
          )}
        </div>
      </div>

      {/* Expandable Live Execution Trace Feed */}
      {showTrace && (
        <div className="flowing-trace-container">
          <div className="flowing-trace-header">
            <span>Live Agent & Tool Calls Trace</span>
            <small>{events.length} events logged</small>
          </div>
          <div className="flowing-trace-feed">
            {events.map((ev, i) => (
              <div
                key={i}
                className={`flowing-trace-item ${ev.warning || ev.error ? 'item-warning' : ev.status === 'complete' || ev.status === 'passed' ? 'item-complete' : ''}`}
              >
                <div className="trace-item-meta">
                  <span className="trace-time">{ev.timestamp || 'now'}</span>
                  {ev.agent && <span className="trace-agent-badge">{ev.agent.replace(' Agent', '')}</span>}
                  {ev.tool && <span className="trace-tool-badge">🛠️ {ev.tool}</span>}
                </div>
                <p className="trace-item-msg">
                  {ev.warning ? (
                    <span className="trace-warning-msg">⚠️ {ev.warning}</span>
                  ) : ev.result ? (
                    <span className="trace-result-msg">📥 {ev.result}</span>
                  ) : (
                    ev.action || ev.detail || ev.stage
                  )}
                </p>
              </div>
            ))}
            <div ref={traceEndRef} />
          </div>
        </div>
      )}

      {/* Micro Progress Bar */}
      <div className="flowing-progress-track">
        <div
          className="flowing-progress-bar"
          style={{
            width: `${((stageIndex + 1) / 6) * 100}%`,
            backgroundColor: activeStage.color,
          }}
        />
      </div>
    </div>
  )
}
