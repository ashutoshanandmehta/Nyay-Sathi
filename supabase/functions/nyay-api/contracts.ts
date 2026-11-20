// Shared contracts and wire schemas for Nyay Saathi Supabase Edge runtime (nyay-api).
// Pure TypeScript, zero Node-only dependencies (compatible with Deno 2 and Vitest).

export type Language = 'en' | 'hi' | 'hinglish'

export type TaskIntent =
  | 'information'
  | 'legal_options'
  | 'draft'
  | 'summary'
  | 'conversation'
  | 'practice'

export type LegalDomain =
  | 'consumer'
  | 'financial_fraud'
  | 'banking'
  | 'criminal'
  | 'employment'
  | 'tenancy'
  | 'rti'
  | 'other_legal'
  | 'general'
  | 'unknown'

export type CaseLink = 'new' | 'existing' | 'unrelated' | 'uncertain'

export type ClaimKind = 'quote' | 'factual' | 'legal' | 'procedure' | 'practical' | 'document' | 'question'

export type BlockType =
  | 'direct_answer'
  | 'immediate_actions'
  | 'recommended_route'
  | 'evidence_checklist'
  | 'document'
  | 'alternatives'
  | 'question'
  | 'human_handoff'

export type ClaimGrounding =
  | 'reported_by_user'
  | 'verified_legal_source'
  | 'practical_precaution'
  | 'requires_confirmation'

export interface MessageSegment {
  id: string
  text: string
}

export interface AgentTask {
  task_id: string
  title: string
  intent: TaskIntent
  domain: LegalDomain
  case_link: CaseLink
  relationship?: string
  source_segment_ids?: string[]
}

export interface AnswerClaim {
  claim_id: string
  task_id: string
  kind: ClaimKind
  block_type?: BlockType
  grounding?: ClaimGrounding
  text: string
  evidence_ids?: string[]
  depends_on?: string[]
  optional?: boolean
  in_document?: boolean
}

export interface PatchValue {
  key?: string
  value?: string
  name?: string
  role?: string
  date?: string
  description?: string
  event_type?: string
  recipient?: string
}

export type PatchOperation =
  | 'fact'
  | 'correction'
  | 'timeline'
  | 'event'
  | 'party'
  | 'location'
  | 'remedy'
  | 'action'
  | 'response'
  | 'outcome'

export interface CasePatch {
  patch_id: string
  task_id: string
  operation: PatchOperation
  payload: PatchValue
  source_refs: string[]
  depends_on?: string[]
}

export interface AgentAnswer {
  central_question: string
  tasks: AgentTask[]
  claims: AnswerClaim[]
  case_patches?: CasePatch[]
  factual_issues?: string[]
  legal_issues?: string[]
  case_stage?: string
  next_action?: string
  risk?: 'ordinary' | 'elevated' | 'urgent'
}

export interface ClaimVerdict {
  claim_id: string
  support: 'supported' | 'unsupported' | 'uncertain'
  reason: string
  requires_public_evidence?: boolean
}

export interface PatchVerdict {
  patch_id: string
  support: 'supported' | 'unsupported' | 'uncertain'
  reason: string
}

export interface AgentReview {
  claims: ClaimVerdict[]
  patch_verdicts?: PatchVerdict[]
  primary_question_answered: boolean
  next_action_useful: boolean
  cross_block_coherent?: boolean
  repair_instructions?: string[]
}

export interface RepairPatch {
  removals?: string[]
  replacements?: AnswerClaim[]
  additions?: AnswerClaim[]
}

export interface ResearchQuestion {
  query: string
  material_gap: string
}

export interface ResearchRequest {
  questions: ResearchQuestion[]
}

export type StreamEventKind = 'progress' | 'safety' | 'answer_block' | 'result' | 'error'

export interface StreamEventEnvelope<TPayload = Record<string, unknown>> {
  schema_version: 'nyay.stream.v1'
  execution_id: string
  request_id: string
  seq: number
  kind: StreamEventKind
  block_id: string | null
  block_revision: number
  publication_status: 'published' | 'superseded' | 'withheld'
  payload: TPayload
}

export interface ResolutionBlock {
  block_id: string
  block_type: BlockType
  title: string
  content: string
  items: string[]
  grounding: ClaimGrounding
  claim_ids: string[]
  source_ids: string[]
  revision: number
  publication_status: 'approved' | 'partial'
  document_title?: string | null
}

export interface SourceCitation {
  passage_id: string
  source_id: string
  title: string
  locator: string
  text: string
  canonical_url: string
  retrieved_at: string
  limitations: string
  citation_number: number
  origin: string
  verification_status?: string
  source_type?: string
  jurisdiction?: string | null
  publication_date?: string | null
  effective_date?: string | null
  certified_proposition?: boolean
  effective_from?: string | null
  effective_until?: string | null
}

export interface FactProvenance {
  source_type: 'message' | 'document'
  source_id: string
  page?: number | null
  span?: string | null
}

export type FactStatusLabel =
  | 'user_allegation'
  | 'user_confirmed'
  | 'document_statement'
  | 'assistant_inference'

export interface FactRecord {
  key?: string
  value: string
  status: FactStatusLabel
  provenance: FactProvenance[]
  previous_values?: Array<{ value: string; updated_at: string }>
  updated_at: string
}

export interface JourneyModel {
  events: Array<{
    id: string
    event_type: string
    description: string
    occurred_at: string | null
    recorded_at: string
    evidence_status: string
    recipient: string | null
    reference: string | null
    supersedes_id: string | null
  }>
  submissions: Array<{
    id: string
    recipient: string
    reference: string | null
    submitted_at: string | null
    channel: string
  }>
  commitments: Array<{
    event_id: string
    description: string
    due_at: string | null
    status: string
  }>
  outcome: string
  satisfaction: string
  severity: string
  recommendations: Array<Record<string, unknown>>
}

export interface CaseMemoryModel {
  version: number
  domain: LegalDomain
  case_stage: string
  parties: Array<Record<string, unknown>>
  locations: Array<Record<string, unknown>>
  facts: Record<string, FactRecord>
  events: Array<Record<string, unknown>>
  timeline: Array<Record<string, unknown>>
  contradictions: Array<{ description?: string; resolved?: boolean }>
  unknowns: string[]
  requested_remedy: string | null
  actions_completed: string[]
  responses_received: Array<Record<string, unknown>>
  correspondence_history: Array<Record<string, unknown>>
  questions_for_legal_review: string[]
  legal_issues_for_review: string[]
  urgent_matters: Array<Record<string, unknown>>
  pending_questions: Array<Record<string, unknown>>
  evidence: Array<Record<string, unknown>>
  stale_draft_ids: string[]
  journey: JourneyModel
}

export function defaultJourney(): JourneyModel {
  return {
    events: [],
    submissions: [],
    commitments: [],
    outcome: 'unknown',
    satisfaction: 'unresolved',
    severity: 'ordinary',
    recommendations: [],
  }
}

export function defaultCaseMemory(): CaseMemoryModel {
  return {
    version: 0,
    domain: 'unknown',
    case_stage: 'intake',
    parties: [],
    locations: [],
    facts: {},
    events: [],
    timeline: [],
    contradictions: [],
    unknowns: [],
    requested_remedy: null,
    actions_completed: [],
    responses_received: [],
    correspondence_history: [],
    questions_for_legal_review: [],
    legal_issues_for_review: [],
    urgent_matters: [],
    pending_questions: [],
    evidence: [],
    stale_draft_ids: [],
    journey: defaultJourney(),
  }
}

export function normalizeCaseMemory(raw: unknown, version = 0): CaseMemoryModel {
  const base = defaultCaseMemory()
  if (!raw || typeof raw !== 'object') return { ...base, version }
  const obj = raw as Record<string, unknown>
  const rawFacts = (obj.facts && typeof obj.facts === 'object' ? obj.facts : {}) as Record<
    string,
    Partial<FactRecord>
  >
  const normalizedFacts: Record<string, FactRecord> = {}
  for (const [k, f] of Object.entries(rawFacts)) {
    if (!f || typeof f !== 'object') continue
    const prov = Array.isArray(f.provenance) ? f.provenance : []
    const inferredStatus: FactStatusLabel =
      f.status &&
      ['user_allegation', 'user_confirmed', 'document_statement', 'assistant_inference'].includes(f.status)
        ? f.status
        : prov.length > 0 && prov.every(p => p?.source_type === 'document')
          ? 'document_statement'
          : 'user_allegation'
    normalizedFacts[k] = {
      key: k,
      value: String(f.value ?? ''),
      status: inferredStatus,
      provenance: prov,
      ...(Array.isArray(f.previous_values) && f.previous_values.length > 0
        ? { previous_values: f.previous_values }
        : {}),
      updated_at: typeof f.updated_at === 'string' ? f.updated_at : new Date().toISOString(),
    }
  }
  const rawJourney = (obj.journey && typeof obj.journey === 'object' ? obj.journey : {}) as Partial<JourneyModel>
  const eventsList = Array.isArray(obj.events)
    ? (obj.events as Array<Record<string, unknown>>)
    : Array.isArray(obj.timeline)
      ? (obj.timeline as Array<Record<string, unknown>>)
      : []

  return {
    version: typeof obj.version === 'number' ? obj.version : version,
    domain: (typeof obj.domain === 'string' ? obj.domain : 'unknown') as LegalDomain,
    case_stage: typeof obj.case_stage === 'string' ? obj.case_stage : 'intake',
    parties: Array.isArray(obj.parties) ? (obj.parties as Array<Record<string, unknown>>) : [],
    locations: Array.isArray(obj.locations) ? (obj.locations as Array<Record<string, unknown>>) : [],
    facts: normalizedFacts,
    events: eventsList,
    timeline: Array.isArray(obj.timeline) ? (obj.timeline as Array<Record<string, unknown>>) : eventsList,
    contradictions: Array.isArray(obj.contradictions)
      ? (obj.contradictions as Array<{ description?: string; resolved?: boolean }>)
      : [],
    unknowns: Array.isArray(obj.unknowns) ? (obj.unknowns as string[]) : [],
    requested_remedy: typeof obj.requested_remedy === 'string' ? obj.requested_remedy : null,
    actions_completed: Array.isArray(obj.actions_completed) ? (obj.actions_completed as string[]) : [],
    responses_received: Array.isArray(obj.responses_received)
      ? (obj.responses_received as Array<Record<string, unknown>>)
      : [],
    correspondence_history: Array.isArray(obj.correspondence_history)
      ? (obj.correspondence_history as Array<Record<string, unknown>>)
      : [],
    questions_for_legal_review: Array.isArray(obj.questions_for_legal_review)
      ? (obj.questions_for_legal_review as string[])
      : [],
    legal_issues_for_review: Array.isArray(obj.legal_issues_for_review)
      ? (obj.legal_issues_for_review as string[])
      : [],
    urgent_matters: Array.isArray(obj.urgent_matters)
      ? (obj.urgent_matters as Array<Record<string, unknown>>)
      : [],
    pending_questions: Array.isArray(obj.pending_questions)
      ? (obj.pending_questions as Array<Record<string, unknown>>)
      : [],
    evidence: Array.isArray(obj.evidence) ? (obj.evidence as Array<Record<string, unknown>>) : [],
    stale_draft_ids: Array.isArray(obj.stale_draft_ids) ? (obj.stale_draft_ids as string[]) : [],
    journey: {
      events: Array.isArray(rawJourney.events) ? rawJourney.events : [],
      submissions: Array.isArray(rawJourney.submissions) ? rawJourney.submissions : [],
      commitments: Array.isArray(rawJourney.commitments) ? rawJourney.commitments : [],
      outcome: typeof rawJourney.outcome === 'string' ? rawJourney.outcome : 'unknown',
      satisfaction: typeof rawJourney.satisfaction === 'string' ? rawJourney.satisfaction : 'unresolved',
      severity: typeof rawJourney.severity === 'string' ? rawJourney.severity : 'ordinary',
      recommendations: Array.isArray(rawJourney.recommendations) ? rawJourney.recommendations : [],
    },
  }
}

/** Deterministic sentence/clause segmenter matching backend/app/routing/segments.py */
export function segmentMessage(message: string): MessageSegment[] {
  const cleaned = (message || '').trim()
  if (!cleaned) return [{ id: 's1', text: '' }]
  const parts = cleaned
    .split(/(?<=[.?!।])\s+|\n+/u)
    .map(p => p.trim())
    .filter(Boolean)
  if (!parts.length) return [{ id: 's1', text: cleaned }]
  return parts.slice(0, 16).map((text, idx) => ({
    id: `s${idx + 1}`,
    text,
  }))
}
