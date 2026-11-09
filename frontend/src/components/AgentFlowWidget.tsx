import { AlertTriangle, CheckCircle2, Cpu, Layers, RotateCw, Scale, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { StreamEvent } from '../types'

export type AgentStageId = 'context' | 'reasoning' | 'research' | 'verifier' | 'repair' | 'final'

export interface AgentFlowWidgetProps {
  isStreaming: boolean
  events: StreamEvent[]
}

// A plain stage label plus one line on what is running; the full trace lives in Settings → Agent Workflow.
const STAGES: { id: AgentStageId; label: string; sublabel: string; icon: typeof Cpu; color: string }[] = [
  { id: 'context', label: 'Reading your case', sublabel: 'Loading facts and certified law', icon: Layers, color: 'var(--jade-ink)' },
  { id: 'reasoning', label: 'Thinking it through', sublabel: 'Drafting the answer and legal claims', icon: Cpu, color: 'var(--jade-ink)' },
  { id: 'research', label: 'Checking the law', sublabel: 'Searching statutes and official portals', icon: Search, color: 'var(--jade-ink)' },
  { id: 'verifier', label: 'Double-checking', sublabel: 'Verifying each claim against its source', icon: Scale, color: 'var(--jade-ink)' },
  { id: 'repair', label: 'Fixing a detail', sublabel: 'Correcting what the verifier flagged', icon: RotateCw, color: 'var(--coral-ink)' },
  { id: 'final', label: 'Almost ready', sublabel: 'Formatting the verified answer', icon: CheckCircle2, color: 'var(--jade-ink)' },
]

function stageOf(stage: string | undefined): AgentStageId {
  const s = stage?.toLowerCase() || ''
  if (['saving', 'context', 'triage', 'intake', 'checks'].includes(s)) return 'context'
  if (['web_research', 'research', 'web_search', 'web_fetch'].includes(s)) return 'research'
  if (['review', 'assess_information'].includes(s)) return 'verifier'
  if (['revision', 'repair', 'fix', 'revise'].includes(s)) return 'repair'
  if (['verify', 'complete', 'result', 'compose', 'structuring'].includes(s)) return 'final'
  return 'reasoning'
}

export default function AgentFlowWidget({ isStreaming, events }: AgentFlowWidgetProps) {
  const [visible, setVisible] = useState(isStreaming)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (isStreaming) {
      setVisible(true)
      setElapsed(0)
      const start = Date.now()
      const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 500)
      return () => clearInterval(timer)
    }
    // Fade out shortly after the answer arrives.
    const timer = setTimeout(() => setVisible(false), 1200)
    return () => clearTimeout(timer)
  }, [isStreaming])

  const activeId = useMemo(() => (events.length ? stageOf(events[events.length - 1].stage) : 'context'), [events])
  if (!visible) return null

  const index = STAGES.findIndex(s => s.id === activeId)
  const stage = STAGES[index]
  const Icon = stage.icon
  const last = events[events.length - 1]
  const problem = last?.warning || last?.error
  const detail = last?.action || last?.detail || last?.result || (last?.passages_count ? `Loaded ${last.passages_count} legal provisions` : stage.sublabel)
  return (
    <div className="flowing-widget" role="status" aria-label={stage.label}>
      <div className="flowing-row" key={stage.id}>
        <Icon size={14} style={{ color: stage.color }} className={stage.id === 'repair' ? 'spin-loop' : 'flowing-icon-breathing'} aria-hidden="true" />
        <span className="flowing-stage-name">{stage.label}…</span>
        <span className="flowing-timer">{index + 1}/{STAGES.length}{isStreaming && ` · ${elapsed}s`}</span>
      </div>
      <div className={`flowing-detail ${problem ? 'warning' : ''}`} title={problem || detail}>
        {problem ? <AlertTriangle size={11} aria-hidden="true" /> : last?.tool && <code>{last.tool}</code>}
        <span>{problem || detail}</span>
      </div>
      <div className="flowing-progress-track">
        <div className="flowing-progress-bar" style={{ width: `${((index + 1) / STAGES.length) * 100}%`, backgroundColor: stage.color }} />
      </div>
    </div>
  )
}
