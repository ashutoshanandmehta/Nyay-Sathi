// Risk-calibrated mechanical verification, disguised-law blocking, dependency propagation,
// case-patch authorization, citation numbering in display order, and resolution block assembly.

import type {
  AgentAnswer,
  AgentReview,
  AnswerClaim,
  BlockType,
  CaseMemoryModel,
  CasePatch,
  ClaimGrounding,
  FactProvenance,
  Language,
  ResolutionBlock,
  SourceCitation,
} from './contracts.ts'
import { segmentMessage } from './contracts.ts'
import type { EvidencePassage } from './knowledge.ts'
import { isPhysicalLibertyCategory } from './safety.ts'

export interface EvidenceEntry {
  evidence_id: string
  kind: 'segment' | 'prior_user_message' | 'fact' | 'document' | 'public'
  text: string
  title?: string
  locator?: string
  canonical_url?: string
  source_id?: string
  origin?: string
  retrieved_at?: string
  limitations?: string
  verification_status?: string
  jurisdiction?: string | null
  publication_date?: string | null
  effective_date?: string | null
  effective_until?: string | null
  certified_proposition?: boolean
  origin_verified?: boolean
  source_type?: string
  generic_snippet?: boolean
}

export class EvidenceRegistry {
  entries: Record<string, EvidenceEntry> = {}
  private publicSet: Set<string> = new Set()

  constructor(state: {
    current_message: string
    prior_user_messages?: Array<{ id: string; content: string }>
    memory?: CaseMemoryModel | Record<string, unknown>
    attachments?: Array<{ id: string; filename: string; extracted_text: string; consent_status?: string }>
    passages?: EvidencePassage[]
  }) {
    const segments = segmentMessage(state.current_message || '')
    for (const seg of segments) {
      const eid = `segment:${seg.id}`
      this.entries[eid] = {
        evidence_id: eid,
        kind: 'segment',
        text: seg.text,
      }
    }
    for (const msg of state.prior_user_messages || []) {
      const eid = `message:${msg.id}`
      this.entries[eid] = {
        evidence_id: eid,
        kind: 'prior_user_message',
        text: msg.content,
      }
    }
    const facts = ((state.memory as CaseMemoryModel | undefined)?.facts || {}) as Record<
      string,
      { value?: unknown }
    >
    for (const [key, fact] of Object.entries(facts)) {
      const eid = `fact:${key}`
      this.entries[eid] = {
        evidence_id: eid,
        kind: 'fact',
        text: String(fact?.value ?? ''),
      }
    }
    for (const att of state.attachments || []) {
      if (att.consent_status && att.consent_status !== 'consented') continue
      const eid = `document:${att.id}`
      this.entries[eid] = {
        evidence_id: eid,
        kind: 'document',
        title: att.filename,
        text: att.extracted_text || '',
      }
    }
    for (const p of state.passages || []) {
      this.registerPublicPassage(p)
    }
  }

  registerPublicPassage(p: EvidencePassage): void {
    this.entries[p.passage_id] = {
      evidence_id: p.passage_id,
      kind: 'public',
      text: p.text,
      title: p.title,
      locator: p.locator,
      canonical_url: p.canonical_url,
      source_id: p.source_id,
      origin: p.origin,
      retrieved_at: p.retrieved_at,
      limitations: p.limitations,
      verification_status: p.verification_status,
      jurisdiction: p.jurisdiction || 'India',
      publication_date: p.publication_date || null,
      effective_date: p.effective_date || null,
      effective_until: p.effective_until || null,
      certified_proposition: p.certified_proposition,
      origin_verified: p.origin_verified,
      source_type: p.source_type,
    }
    this.publicSet.add(p.passage_id)
  }

  publicIds(): Set<string> {
    return new Set(this.publicSet)
  }
}

export const TEMPLATES: Record<string, Record<Language, string>> = {
  no_verified_answer: {
    en: "I couldn't verify enough reliable legal information to answer this safely just now, so I haven't given a legal conclusion. You can ask again with a few more details (your state, the dates, and what papers you have), or speak to a local lawyer or your District Legal Services Authority.",
    hi: 'अभी मैं इसका सुरक्षित जवाब देने लायक भरोसेमंद कानूनी जानकारी सत्यापित नहीं कर सका, इसलिए मैंने कोई कानूनी निष्कर्ष नहीं दिया है। आप थोड़ी और जानकारी (आपका राज्य, तारीखें और आपके पास कौन से कागज़ हैं) के साथ फिर से पूछ सकते हैं, या किसी स्थानीय वकील या अपने ज़िला विधिक सेवा प्राधिकरण से बात कर सकते हैं।',
    hinglish:
      'Abhi main iska safe jawab dene layak reliable legal information verify nahi kar paya, isliye maine koi legal conclusion nahi diya hai. Aap thodi aur details (aapka state, dates, aur aapke paas kaun se papers hain) ke saath dobara pooch sakte hain, ya kisi local lawyer ya apne District Legal Services Authority se baat kar sakte hain.',
  },
  handoff_safety: {
    en: 'Once you are safe, a lawyer can help you get legal protection. If paying a lawyer is difficult, ask the District Legal Services Authority (DLSA) whether you qualify for free legal aid.',
    hi: 'सुरक्षित होने के बाद, एक वकील आपको कानूनी सुरक्षा दिलाने में मदद कर सकता है। अगर वकील की फीस देना मुश्किल है, तो ज़िला विधिक सेवा प्राधिकरण (DLSA) से पूछें कि क्या आप मुफ़्त कानूनी सहायता के पात्र हैं।',
    hinglish:
      'Safe hone ke baad, ek lawyer aapko legal protection dilane mein madad kar sakta hai. Agar lawyer ki fees dena mushkil hai, to District Legal Services Authority (DLSA) se poochhein ki kya aap free legal aid ke liye eligible hain.',
  },
  handoff_liberty: {
    en: "Because someone's liberty is involved, speak to a criminal lawyer as soon as you can, ideally before any bail hearing or before giving a statement. If paying a lawyer is difficult, ask the District Legal Services Authority (DLSA) at the district court whether you qualify for free legal aid.",
    hi: 'क्योंकि किसी की आज़ादी का सवाल है, जितनी जल्दी हो सके किसी आपराधिक मामलों के वकील से बात करें, बेहतर हो कि ज़मानत की सुनवाई या कोई बयान देने से पहले। अगर वकील की फीस देना मुश्किल है, तो ज़िला अदालत में ज़िला विधिक सेवा प्राधिकरण (DLSA) से पूछें कि क्या आप मुफ़्त कानूनी सहायता के पात्र हैं।',
    hinglish:
      'Kyunki kisi ki azaadi ka sawal hai, jitni jaldi ho sake kisi criminal lawyer se baat karein, behtar ho ki bail hearing ya koi statement dene se pehle. Agar lawyer ki fees dena mushkil hai, to district court mein District Legal Services Authority (DLSA) se poochhein ki kya aap free legal aid ke liye eligible hain.',
  },
  configuration: {
    en: 'AI configuration required: Your message is saved in this chat. Add your OpenAI API key or configure the backend to enable researched answers. You can still organize documents and export your case.',
    hi: 'AI configuration required: आपका संदेश इस चैट में सुरक्षित है। शोध वाले जवाब चालू करने के लिए OpenAI कुंजी सेटअप करें। दस्तावेज़ व्यवस्थित करना और केस एक्सपोर्ट करना उपलब्ध है।',
    hinglish:
      'AI configuration required: Aapka message is chat mein saved hai. Researched answers ke liye OpenAI key configure karein. Documents organize aur case export kar sakte hain.',
  },
}

export function templateText(id: string, language: Language = 'en'): string {
  const entry = TEMPLATES[id] || TEMPLATES.no_verified_answer
  return entry[language] || entry.en
}

const DISGUISED_CONSEQUENTIAL_RE =
  /(?:\b(?:section|sec\.|article|rule\s+\d+|order\s+(?!id\b)[ivxlcdm\d]+\b|act,\s*\d{4}|bns|bnss|bsa|ipc|crpc|cpa\s*2019)\b|\b(?:must\s+(?:refund|pay|register|accept|release)|legally\s+(?:entitled|required|bound|mandatory)|statutory\s+(?:right|deadline|limit)|limitation\s+period|within\s+\d+\s*(?:days?|hours?|months?|years?)\s+(?:under|by\s+law|from\s+cause))\b|\b(?:confront\s+them|physically\s+resist|refuse\s+custody|block\s+the\s+police)\b|\b(?:call\s+\d{3,5}|helpline\s+\d{3,5}|\+?91[-\s]?\d{10})\b)/i

const REVIEW_REQUIRED_RE =
  /\b(?:courts?|commissions?|tribunals?|forums?|bench|judges?|magistrates?)\b[\s\S]{0,60}\b(?:held|holds|ruled|rules|ordered|directed|awarded|decided|struck|upheld|quashed)\b|\b(?:precedents?|rulings?|judg(?:e)?ments?|verdicts?|case\s+law|landmark|in\s+similar\s+cases|courts?\s+have)\b|\b\d+\s*(?:days?|weeks?|months?|years?|din)\b|\b(?:double|twice|triple)\s+the\b|\d+(?:\.\d+)?\s*%|\b(?:entitled|illegal|unlawful|offen[cs]es?|punishable|bailable|non-bailable|compoundable|liable|penalty|fine\s+of)\b|धारा|अदालत|न्यायालय|फैसला|कानूनन|अवैध|जुर्माना|दोगुना|\d+\s*दिन/iu

const CASE_NAME_RE = /\b[A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*)*\s+(?:v\.|vs\.?|versus)\s+[A-Z]/

const SECTION_REF_RE =
  /\b(?:sections?|secs?\.)\s*(\d+[A-Za-z]?)(?:\(\d+\))?(?:\s*(?:,|and|&|to|-|–)\s*(\d+[A-Za-z]?)(?:\(\d+\))?)?/gi

const PCA_SEVEN_DAY_PROVISO_RE = /\b(?:seven[- ]day|7[- ]day|within\s+(?:seven|7)\s+days)\b/i
const PCA_BRIBE_CONTEXT_RE =
  /\b(?:prevention\s+of\s+corruption|undue\s+advantage|compelled\s+to\s+(?:give|pay)|bribe|anti[- ]corruption)\b/i

export function hasDisguisedConsequentialAssertion(text: string): boolean {
  return DISGUISED_CONSEQUENTIAL_RE.test(text || '')
}

export function needsSemanticReview(text: string): boolean {
  const t = text || ''
  return hasDisguisedConsequentialAssertion(t) || REVIEW_REQUIRED_RE.test(t) || CASE_NAME_RE.test(t)
}

function isCertifiedOrOfficialPublicEntry(entry: EvidenceEntry): boolean {
  if (entry.generic_snippet) return false
  if (entry.certified_proposition || entry.origin_verified) return true
  if (entry.source_type === 'indian_official') return true
  try {
    const host = new URL(entry.canonical_url || '').hostname.toLowerCase()
    return host.endsWith('.gov.in') || host.endsWith('.nic.in') || host === 'rbi.org.in' || host === 'www.rbi.org.in'
  } catch {
    return false
  }
}

function extractSections(text: string): Set<string> {
  const out = new Set<string>()
  const re = new RegExp(SECTION_REF_RE.source, 'gi')
  let match: RegExpExecArray | null
  while ((match = re.exec(text || '')) !== null) {
    if (match[1]) out.add(match[1].toUpperCase())
    if (match[2]) out.add(match[2].toUpperCase())
  }
  return out
}

export function checkPinpointStatutoryAlignment(claim: AnswerClaim, registry: EvidenceRegistry): string | null {
  const publicIds = registry.publicIds()
  const citedPublic = (claim.evidence_ids || []).filter(k => publicIds.has(k)).map(k => registry.entries[k])
  if (!citedPublic.length) return null

  const text = claim.text || ''
  if (PCA_SEVEN_DAY_PROVISO_RE.test(text) && PCA_BRIBE_CONTEXT_RE.test(text)) {
    const hasSection8 = citedPublic.some(e =>
      extractSections(`${e.locator || ''} ${e.text || ''}`).has('8')
    )
    if (!hasSection8) return 'pinpoint_locator_mismatch'
  }

  const claimedSections = extractSections(text)
  if (!claimedSections.size) return null

  const sourceSections = new Set<string>()
  for (const entry of citedPublic) {
    for (const s of extractSections(`${entry.locator || ''} ${entry.text || ''}`)) {
      sourceSections.add(s)
    }
  }
  if (sourceSections.size > 0) {
    for (const cs of claimedSections) {
      if (!sourceSections.has(cs)) return 'pinpoint_locator_mismatch'
    }
  }
  return null
}

const TERMINAL_PUNCTUATION = new Set(['.', '?', '!', ':', ')', '”', '"', ']', '।'])

export function isSentenceComplete(text: string): boolean {
  const stripped = (text || '').trim()
  if (!stripped) return false
  const lines = stripped
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
  if (lines.every(line => /^(?:[-*•]|\d+[.)]|\||#+)\s*/.test(line))) return true
  if (lines.every(line => line.startsWith('|'))) return true
  if (stripped.startsWith('#')) return true
  return TERMINAL_PUNCTUATION.has(stripped[stripped.length - 1])
}

export interface MechanicalCheckResult {
  blocked: Record<string, string>
  approved: Record<string, string>
  pending: string[]
}

export function mechanicalChecks(answer: AgentAnswer, registry: EvidenceRegistry): MechanicalCheckResult {
  const blocked: Record<string, string> = {}
  const approved: Record<string, string> = {}
  const pending: string[] = []
  const ids = new Set(answer.claims.map(c => c.claim_id))
  const publicIds = registry.publicIds()
  const physicalLibertyUrgent = answer.risk === 'urgent'

  for (const claim of answer.claims) {
    const eids = claim.evidence_ids || []
    const deps = claim.depends_on || []
    let reason: string | null = null
    const needsLegalAuthority =
      claim.kind === 'legal' || claim.kind === 'procedure' || claim.grounding === 'verified_legal_source'

    if (eids.some(k => !(k in registry.entries))) {
      reason = 'unknown_evidence'
    } else if (deps.some(k => !ids.has(k) || k === claim.claim_id)) {
      reason = 'invalid_dependency'
    } else if (
      /https?:\/\/|\[Source:|\]\(|\b(?:I (?:have )?(?:filed|sent|saved|signed|updated)|I am (?:your |a )?(?:lawyer|advocate))\b/i.test(
        claim.text
      )
    ) {
      reason = 'untrusted_link_or_execution_claim'
    } else if (needsLegalAuthority && !eids.some(k => publicIds.has(k))) {
      reason = 'missing_public_evidence'
    } else if (
      needsLegalAuthority &&
      !eids.some(k => publicIds.has(k) && isCertifiedOrOfficialPublicEntry(registry.entries[k]))
    ) {
      reason = 'uncertified_or_generic_legal_source'
    } else {
      const pinpointErr = checkPinpointStatutoryAlignment(claim, registry)
      if (pinpointErr) {
        reason = pinpointErr
      } else if (
        claim.kind !== 'question' &&
        eids.length === 0 &&
        !(
          claim.kind === 'practical' &&
          claim.grounding === 'practical_precaution' &&
          !claim.in_document &&
          !hasDisguisedConsequentialAssertion(claim.text)
        )
      ) {
        reason = 'missing_claim_evidence'
      }
    }

    if (
      reason === 'missing_claim_evidence' &&
      claim.in_document &&
      (claim.kind === 'document' || claim.kind === 'practical') &&
      claim.grounding === 'practical_precaution'
    ) {
      pending.push(claim.claim_id)
    } else if (reason) {
      blocked[claim.claim_id] = reason
    } else if (!isSentenceComplete(claim.text)) {
      pending.push(claim.claim_id)
    } else if (claim.kind === 'quote') {
      const privateEntries = eids.filter(k => !publicIds.has(k)).map(k => registry.entries[k])
      if (
        claim.text.trim() &&
        privateEntries.some(e => e.text.includes(claim.text)) &&
        claim.text.length <= 3000
      ) {
        approved[claim.claim_id] = 'attributed_exact_extract'
      } else {
        blocked[claim.claim_id] = 'quote_not_in_private_evidence'
      }
    } else if (
      !physicalLibertyUrgent &&
      (claim.grounding === 'reported_by_user' || claim.grounding === 'practical_precaution') &&
      (claim.kind === 'factual' || claim.kind === 'practical' || claim.kind === 'document') &&
      claim.block_type !== 'recommended_route' &&
      claim.block_type !== 'human_handoff' &&
      claim.text.trim() &&
      !needsSemanticReview(claim.text) &&
      eids.every(k => k in registry.entries && !publicIds.has(k))
    ) {
      approved[claim.claim_id] = 'risk_calibrated_consistency'
    } else if (
      !physicalLibertyUrgent &&
      claim.kind === 'question' &&
      claim.grounding === 'requires_confirmation' &&
      claim.text.includes('?') &&
      claim.text.length <= 400 &&
      !needsSemanticReview(claim.text)
    ) {
      approved[claim.claim_id] = 'non_assertive_clarification'
    } else {
      pending.push(claim.claim_id)
    }
  }

  return { blocked, approved, pending }
}

export function applyReviewVerdicts(
  review: AgentReview,
  pendingIds: string[],
  answer: AgentAnswer,
  registry: EvidenceRegistry
): Record<string, string> {
  const accepted: Record<string, string> = {}
  const publicIds = registry.publicIds()
  const claimMap = new Map(answer.claims.map(c => [c.claim_id, c]))
  const pendingSet = new Set(pendingIds)

  for (const verdict of review.claims || []) {
    const claim = claimMap.get(verdict.claim_id)
    if (!claim) continue
    if (verdict.support !== 'supported') continue
    const eids = claim.evidence_ids || []
    const hasPublic = eids.some(k => publicIds.has(k))
    if (verdict.requires_public_evidence && !hasPublic) {
      continue
    }
    if (hasDisguisedConsequentialAssertion(claim.text) && !hasPublic) {
      continue
    }
    if (pendingSet.has(claim.claim_id)) {
      accepted[claim.claim_id] = 'independent_semantic_review'
    }
  }
  return accepted
}

export function propagateDependencies(
  answer: AgentAnswer,
  accepted: Record<string, string>
): Record<string, string> {
  const done = new Set<string>()
  while (true) {
    const ready = answer.claims
      .filter(
        c =>
          c.claim_id in accepted &&
          !done.has(c.claim_id) &&
          (c.depends_on || []).every(dep => done.has(dep))
      )
      .map(c => c.claim_id)
    if (!ready.length) break
    for (const id of ready) done.add(id)
  }
  const result: Record<string, string> = {}
  for (const [k, v] of Object.entries(accepted)) {
    if (done.has(k)) result[k] = v
  }
  return result
}

export function preserveSafePractical(
  answer: AgentAnswer,
  accepted: Record<string, string>,
  blocked: Record<string, string>,
  registry: EvidenceRegistry
): void {
  const publicIds = registry.publicIds()
  for (const claim of answer.claims) {
    if (claim.claim_id in accepted || claim.claim_id in blocked) continue
    if (
      claim.kind === 'practical' &&
      claim.grounding === 'practical_precaution' &&
      claim.block_type === 'immediate_actions' &&
      !claim.in_document &&
      !needsSemanticReview(claim.text) &&
      (claim.evidence_ids || []).every(k => k in registry.entries && !publicIds.has(k))
    ) {
      accepted[claim.claim_id] = 'safe_practical_precaution_fallback'
    }
  }
}

/**
 * Case-write authorization gate:
 * Answer approval NEVER independently authorizes case-state writes.
 * General education ('information') or 'unrelated' / 'uncertain' tasks can only be staged, never committed!
 */
export function authorizeCasePatches(options: {
  answer: AgentAnswer
  review: AgentReview | null
  registry: EvidenceRegistry
  currentMemory: CaseMemoryModel
  requestId?: string
  nowIso?: string
}): {
  updatedMemory: CaseMemoryModel
  committedPatches: Array<Record<string, unknown>>
  stagedPatches: Array<Record<string, unknown>>
  caseProposals: Array<{
    message_id: string
    base_version: number
    status: string
    proposed_facts: Record<string, Record<string, unknown>>
  }>
} {
  const nowIso = options.nowIso || new Date().toISOString()
  const updated: CaseMemoryModel = JSON.parse(JSON.stringify(options.currentMemory))
  const committedPatches: Array<Record<string, unknown>> = []
  const stagedPatches: Array<Record<string, unknown>> = []
  const proposedFactsForUi: Record<string, Record<string, unknown>> = {}
  const patches = options.answer.case_patches || []
  if (!patches.length) {
    return { updatedMemory: updated, committedPatches, stagedPatches, caseProposals: [] }
  }

  const taskById = new Map(options.answer.tasks.map(t => [t.task_id, t]))
  const verdictById = new Map((options.review?.patch_verdicts || []).map(v => [v.patch_id, v]))
  const publicIds = options.registry.publicIds()
  const duplicateIds = new Set(
    patches.map(p => p.patch_id).filter((id, idx, arr) => arr.indexOf(id) !== idx)
  )
  const appliedIds = new Set<string>()

  for (const patch of patches) {
    const task = taskById.get(patch.task_id)
    const verdict = verdictById.get(patch.patch_id)
    const privateRefs = (patch.source_refs || []).filter(r => r in options.registry.entries && !publicIds.has(r))
    const allRefsValid =
      (patch.source_refs || []).length > 0 &&
      (patch.source_refs || []).every(r => r in options.registry.entries && !publicIds.has(r))
    const depsOk = (patch.depends_on || []).every(dep => appliedIds.has(dep))

    // Enforce segment-level scope when task specifies source_segment_ids
    const taskSegments = new Set(task?.source_segment_ids || [])
    const referencedSegments = (patch.source_refs || [])
      .filter(r => r.startsWith('segment:'))
      .map(r => r.slice('segment:'.length))
    const segmentScopeOk =
      taskSegments.size === 0 || referencedSegments.every(segId => taskSegments.has(segId))

    const authorizedForCaseCommit =
      Boolean(task) &&
      !duplicateIds.has(patch.patch_id) &&
      depsOk &&
      segmentScopeOk &&
      (task!.case_link === 'new' || task!.case_link === 'existing') &&
      task!.intent !== 'information' &&
      task!.intent !== 'practice' &&
      verdict?.support === 'supported' &&
      allRefsValid &&
      privateRefs.length > 0

    const recordStaged = (reason: string) => {
      stagedPatches.push({
        patch,
        decision: 'staged_requires_case_authorization',
        reason,
        staged_at: nowIso,
      })
      if ((patch.operation === 'fact' || patch.operation === 'correction') && patch.payload.key && patch.payload.value) {
        proposedFactsForUi[patch.payload.key.trim()] = {
          value: patch.payload.value.trim(),
          status: 'assistant_inference',
        }
      }
    }

    if (!authorizedForCaseCommit) {
      const reason =
        verdict?.support !== 'supported'
          ? 'patch_not_verified_by_reviewer'
          : !segmentScopeOk
            ? 'source_segment_outside_task_scope'
            : !depsOk || duplicateIds.has(patch.patch_id)
              ? 'invalid_patch_identity_or_dependency'
              : !allRefsValid
                ? 'fact_provenance_must_be_private_case_evidence'
                : 'task_not_authorized_to_mutate_case_state'
      recordStaged(reason)
      continue
    }

    const provenance: FactProvenance[] = privateRefs.map(ref => {
      if (ref.startsWith('document:')) {
        return { source_type: 'document', source_id: ref.slice('document:'.length) }
      }
      return { source_type: 'message', source_id: ref }
    })
    const allFromDocument = provenance.length > 0 && provenance.every(p => p.source_type === 'document')
    const baseStatus = allFromDocument ? 'document_statement' : 'user_allegation'

    if (patch.operation === 'fact' || patch.operation === 'correction') {
      const key = (patch.payload.key || '').trim()
      const newVal = (patch.payload.value || '').trim()
      if (!key || !newVal) {
        recordStaged('missing_fact_key_or_value')
        continue
      }
      const existing = updated.facts[key]
      const previousValues = existing && existing.value !== newVal
        ? [...(existing.previous_values || []), { value: existing.value, updated_at: existing.updated_at }]
        : existing?.previous_values || []
      updated.facts[key] = {
        key,
        value: newVal,
        status: existing && existing.value !== newVal ? 'user_confirmed' : baseStatus,
        provenance,
        ...(previousValues.length ? { previous_values: previousValues } : {}),
        updated_at: nowIso,
      }
    } else if (patch.operation === 'remedy') {
      const val = (patch.payload.value || patch.payload.description || '').trim()
      if (!val) {
        recordStaged('missing_remedy_value')
        continue
      }
      updated.requested_remedy = val
    } else if (patch.operation === 'party') {
      const name = (patch.payload.name || patch.payload.value || '').trim()
      const role = (patch.payload.role || patch.payload.key || 'opposite_party').trim()
      if (!name) {
        recordStaged('missing_party_name')
        continue
      }
      updated.parties = [...(updated.parties || []), { name, role, status: baseStatus }]
    } else if (patch.operation === 'location') {
      const val = (patch.payload.value || patch.payload.name || '').trim()
      if (!val) {
        recordStaged('missing_location_value')
        continue
      }
      updated.locations = [
        ...(updated.locations || []),
        { value: val, role: patch.payload.role || patch.payload.key || 'jurisdiction', status: baseStatus },
      ]
    } else if (patch.operation === 'timeline' || patch.operation === 'event') {
      const desc = (patch.payload.description || patch.payload.value || '').trim()
      const date = (patch.payload.date || patch.payload.key || '').trim() || null
      if (!desc) {
        recordStaged('missing_event_description')
        continue
      }
      const evRecord = {
        date: date || 'Date to check',
        description: desc,
        status: baseStatus,
        event_type: patch.payload.event_type || 'reported_event',
        recipient: patch.payload.recipient || null,
      }
      updated.events = [...(updated.events || []), evRecord]
      updated.timeline = [...(updated.timeline || []), evRecord]
      updated.journey.events = [
        ...(updated.journey.events || []),
        {
          id: `jev-${patch.patch_id}`,
          event_type: patch.payload.event_type || 'reported_event',
          description: desc,
          occurred_at: date,
          recorded_at: nowIso,
          evidence_status: baseStatus,
          recipient: patch.payload.recipient || null,
          reference: null,
          supersedes_id: null,
        },
      ]
    } else if (patch.operation === 'action') {
      const desc = (patch.payload.description || patch.payload.value || '').trim()
      if (!desc) {
        recordStaged('missing_action_description')
        continue
      }
      if (!updated.actions_completed.includes(desc)) {
        updated.actions_completed = [...updated.actions_completed, desc]
      }
    } else if (patch.operation === 'response') {
      const desc = (patch.payload.description || patch.payload.value || '').trim()
      if (!desc) {
        recordStaged('missing_response_description')
        continue
      }
      updated.responses_received = [...(updated.responses_received || []), { description: desc, recorded_at: nowIso }]
    } else if (patch.operation === 'outcome') {
      const desc = (patch.payload.description || patch.payload.value || '').trim()
      if (!desc) {
        recordStaged('missing_outcome_description')
        continue
      }
      updated.journey.outcome = desc
    }

    if (task && task.domain && task.domain !== 'unknown' && task.domain !== 'general') {
      updated.domain = task.domain
    }
    appliedIds.add(patch.patch_id)
    committedPatches.push({
      patch,
      decision: 'committed',
      provenance,
      committed_at: nowIso,
    })
  }

  if (committedPatches.length > 0) {
    updated.version = options.currentMemory.version + 1
  }

  const caseProposals =
    Object.keys(proposedFactsForUi).length > 0
      ? [
          {
            message_id: options.requestId || `proposal-${nowIso}`,
            base_version: options.currentMemory.version,
            status: 'staged',
            proposed_facts: proposedFactsForUi,
          },
        ]
      : []

  return {
    updatedMemory: updated,
    committedPatches,
    stagedPatches,
    caseProposals,
  }
}

const URGENT_BLOCK_ORDER: BlockType[] = [
  'direct_answer',
  'immediate_actions',
  'recommended_route',
  'alternatives',
  'evidence_checklist',
  'document',
  'question',
  'human_handoff',
]

const NON_URGENT_BLOCK_ORDER: BlockType[] = [
  'direct_answer',
  'recommended_route',
  'immediate_actions',
  'alternatives',
  'evidence_checklist',
  'document',
  'question',
  'human_handoff',
]

export const BLOCK_TITLES: Record<BlockType, Record<Language, string>> = {
  direct_answer: { en: 'In short', hi: 'संक्षेप में', hinglish: 'Short mein' },
  immediate_actions: {
    en: 'What you can do today',
    hi: 'आज आप क्या कर सकते हैं',
    hinglish: 'Aaj aap kya kar sakte hain',
  },
  recommended_route: { en: "What I'd suggest", hi: 'मेरी सलाह', hinglish: 'Meri salah' },
  alternatives: {
    en: "If that doesn't work",
    hi: 'अगर इससे बात न बने',
    hinglish: 'Agar isse baat na bane',
  },
  evidence_checklist: {
    en: 'Keep these ready',
    hi: 'ये चीज़ें तैयार रखें',
    hinglish: 'Ye cheezein ready rakhein',
  },
  document: {
    en: "Here's a draft you can use",
    hi: 'आपके लिए एक मसौदा',
    hinglish: 'Aapke liye ek draft',
  },
  question: {
    en: 'One thing that would help me',
    hi: 'एक बात बताइए',
    hinglish: 'Ek baat bataiye',
  },
  human_handoff: {
    en: 'When a lawyer would help',
    hi: 'वकील की मदद कब लें',
    hinglish: 'Vakil ki madad kab lein',
  },
}

const MODEL_CITATION_NUMBER_RE = /[ \t]?(?:\[\d{1,2}\])+(?![(\[:])/g
const EVIDENCE_ID_MARKER_RE =
  /[ \t]?\[(?:(?:segment|message|fact|document|attachment):[^\]\s]+|(?:prop|pack|web|cert|corpus|official)-[\w.:-]+)\]/gi

export function inferBlockType(claim: AnswerClaim): BlockType {
  if (claim.block_type) return claim.block_type
  if (claim.in_document || claim.kind === 'document') return 'document'
  if (claim.kind === 'question') return 'question'
  if (claim.kind === 'procedure') return 'recommended_route'
  if (claim.kind === 'practical') return 'immediate_actions'
  return 'direct_answer'
}

export function claimUsesLegalSource(claim: AnswerClaim, btype: BlockType): boolean {
  if (btype === 'evidence_checklist' || btype === 'document' || btype === 'question') return false
  if (
    (claim.kind === 'practical' || claim.kind === 'factual' || claim.kind === 'quote') &&
    claim.grounding !== 'verified_legal_source'
  ) {
    return false
  }
  return claim.kind === 'legal' || claim.kind === 'procedure' || claim.grounding === 'verified_legal_source'
}

export function formatClaimText(claim: AnswerClaim): string {
  if (claim.kind === 'quote') return `You report: “${claim.text}”`
  if (claim.in_document) return claim.text.replace(EVIDENCE_ID_MARKER_RE, '')
  return claim.text.replace(EVIDENCE_ID_MARKER_RE, '').replace(MODEL_CITATION_NUMBER_RE, '')
}

export function appendCitationMarkers(text: string, numbers: number[]): string {
  if (!numbers.length) return text
  const markers = numbers.map(n => `[${n}](#cite-${n})`).join('')
  const body = text.replace(/\s+$/, '')
  const lines = body.split('\n')
  const lastLine = (lines[lines.length - 1] || '').trimStart()
  const separator =
    lastLine.startsWith('|') || lastLine.startsWith('#') || lastLine.startsWith('```') ? '\n\n' : ' '
  return body + separator + markers
}

export function stripCitationMarkers(text: string): string {
  return (text || '')
    .replace(/[ \t]*(?:\[\d+\]\(#cite-\d+\))+/g, '')
    .replace(/\n*\[Source:[^\]]+\]/g, '')
    .trim()
}

export function assembleResolutionBlocks(options: {
  answer: AgentAnswer
  accepted: Record<string, string>
  registry: EvidenceRegistry
  language: Language
  safetyMessages?: Array<Record<string, unknown>>
  urgentContinuation?: boolean
}): {
  content: string
  blocks: ResolutionBlock[]
  sources: SourceCitation[]
  approvedDocuments: Array<{ title: string; content: string; task_id: string }>
  publicationStatus: 'supported' | 'partial' | 'fallback'
} {
  const { answer, accepted, registry, language } = options
  const publicIds = registry.publicIds()
  const isUrgent =
    answer.risk === 'urgent' ||
    Boolean(options.urgentContinuation) ||
    (options.safetyMessages || []).some(m => isPhysicalLibertyCategory(m.category as string))

  const order = isUrgent ? URGENT_BLOCK_ORDER : NON_URGENT_BLOCK_ORDER

  // If any in_document claim was rejected, withhold all document claims so no incomplete draft is saved/shown.
  const anyDocumentRejected = answer.claims.some(c => (c.in_document || c.kind === 'document') && !(c.claim_id in accepted))

  const grouped = new Map<BlockType, AnswerClaim[]>()
  for (const btype of order) grouped.set(btype, [])

  for (const claim of answer.claims) {
    if (!(claim.claim_id in accepted)) continue
    const btype = inferBlockType(claim)
    if (btype === 'human_handoff') continue // Only runtime-guaranteed referral is rendered for handoff
    if ((claim.in_document || btype === 'document') && anyDocumentRejected) continue
    grouped.get(btype)?.push(claim)
  }

  const citationByPassageId = new Map<string, number>()
  const sources: SourceCitation[] = []

  const assignCitationNumber = (passageId: string): number | null => {
    if (!publicIds.has(passageId)) return null
    if (citationByPassageId.has(passageId)) return citationByPassageId.get(passageId)!
    const entry = registry.entries[passageId]
    if (!entry) return null
    const nextNum = sources.length + 1
    citationByPassageId.set(passageId, nextNum)
    sources.push({
      passage_id: passageId,
      source_id: entry.source_id || passageId,
      title: entry.title || 'Official Source',
      locator: entry.locator || '',
      text: entry.text || '',
      canonical_url: entry.canonical_url || '',
      retrieved_at: entry.retrieved_at || '2026-11-07T00:00:00Z',
      limitations: entry.limitations || 'Applicability assessed per claim.',
      citation_number: nextNum,
      origin: entry.origin || 'certified_proposition',
      verification_status: entry.verification_status || (entry.certified_proposition ? 'editor_certified' : 'official_origin_pending_answer_review'),
      source_type: entry.source_type || 'indian_official',
      jurisdiction: entry.jurisdiction || 'India',
      publication_date: entry.publication_date || entry.effective_date || null,
      effective_date: entry.effective_date || null,
      effective_from: entry.effective_date || null,
      effective_until: entry.effective_until || null,
      certified_proposition: entry.certified_proposition,
    })
    return nextNum
  }

  const blocks: ResolutionBlock[] = []
  const approvedDocuments: Array<{ title: string; content: string; task_id: string }> = []

  const extractBlockItems = (text: string): string[] => {
    const lines = text
      .split('\n')
      .map(l => l.trim())
      .filter(Boolean)
    if (lines.length <= 1) return lines
    return lines.map(l => l.replace(/^(?:[-*•●]|\d+[.)]|Step\s+\d+[:.])\s*/i, '').trim()).filter(Boolean)
  }

  for (const btype of order) {
    const claims = grouped.get(btype) || []
    if (!claims.length) continue

    const renderedClaims: string[] = []
    const blockSourceIds = new Set<string>()
    const groundings: ClaimGrounding[] = []
    let docTitle: string | null = null

    for (const claim of claims) {
      let formatted = formatClaimText(claim)
      if (claimUsesLegalSource(claim, btype)) {
        const nums: number[] = []
        for (const eid of claim.evidence_ids || []) {
          const num = assignCitationNumber(eid)
          if (num !== null && !nums.includes(num)) {
            nums.push(num)
            blockSourceIds.add(eid)
          }
        }
        nums.sort((a, b) => a - b)
        formatted = appendCitationMarkers(formatted, nums)
      }
      renderedClaims.push(formatted)
      groundings.push(
        claim.grounding ||
          (blockSourceIds.size > 0
            ? 'verified_legal_source'
            : claim.kind === 'quote' || claim.kind === 'factual'
              ? 'reported_by_user'
              : 'practical_precaution')
      )

      if (claim.in_document || btype === 'document') {
        const task = answer.tasks.find(t => t.task_id === claim.task_id)
        docTitle = task?.title || 'Prepared Correspondence Draft'
        approvedDocuments.push({
          title: docTitle,
          content: formatted,
          task_id: claim.task_id,
        })
      }
    }

    const dominantGrounding: ClaimGrounding = groundings.includes('verified_legal_source')
      ? 'verified_legal_source'
      : groundings.includes('reported_by_user') && !groundings.includes('practical_precaution')
        ? 'reported_by_user'
        : groundings.includes('requires_confirmation') && groundings.every(g => g === 'requires_confirmation')
          ? 'requires_confirmation'
          : 'practical_precaution'

    const joinedContent = renderedClaims.join('\n\n')
    blocks.push({
      block_id: `block-${btype}`,
      block_type: btype,
      title: BLOCK_TITLES[btype][language] || BLOCK_TITLES[btype].en,
      content: joinedContent,
      items: extractBlockItems(joinedContent),
      grounding: dominantGrounding,
      claim_ids: claims.map(c => c.claim_id),
      source_ids: Array.from(blockSourceIds),
      revision: 1,
      publication_status: 'approved',
      ...(docTitle ? { document_title: docTitle } : {}),
    })
  }

  // Runtime-guaranteed human handoff on physical-liberty / urgent turns
  if (isUrgent && blocks.length > 0) {
    const handoffText = templateText('handoff_safety', language)
    blocks.push({
      block_id: 'block-human_handoff',
      block_type: 'human_handoff',
      title: BLOCK_TITLES.human_handoff[language] || BLOCK_TITLES.human_handoff.en,
      content: handoffText,
      items: [handoffText],
      grounding: 'practical_precaution',
      claim_ids: ['runtime-handoff'],
      source_ids: [],
      revision: 1,
      publication_status: 'approved',
    })
  }

  const nonOptionalRejected = answer.claims.some(
    c => !c.optional && inferBlockType(c) !== 'human_handoff' && !(c.claim_id in accepted)
  )

  if (blocks.length === 0) {
    const fallbackText = templateText('no_verified_answer', language)
    return {
      content: fallbackText,
      blocks: [
        {
          block_id: 'block-direct_answer',
          block_type: 'direct_answer',
          title: BLOCK_TITLES.direct_answer[language] || BLOCK_TITLES.direct_answer.en,
          content: fallbackText,
          items: [fallbackText],
          grounding: 'requires_confirmation',
          claim_ids: ['runtime-fallback'],
          source_ids: [],
          revision: 1,
          publication_status: 'partial',
        },
      ],
      sources: [],
      approvedDocuments: [],
      publicationStatus: 'fallback',
    }
  }

  const content = blocks.map(b => b.content).join('\n\n')
  return {
    content,
    blocks,
    sources,
    approvedDocuments,
    publicationStatus: nonOptionalRejected ? 'partial' : 'supported',
  }
}
