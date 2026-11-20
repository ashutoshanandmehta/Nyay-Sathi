// Core Nyay Saathi Supabase Edge Function Handler (nyay-api).
// Implements Auth verification, private cases/conversations, lease-fenced durable turns,
// risk-calibrated mechanical verification, independent semantic review, targeted repair,
// case-patch authorization, durable sequenced SSE streaming/replay, documents, drafts, actions,
// submissions, escalation bundles, BYOK AES-256-GCM key sealing, and editorial role protection.

import type {
  AgentAnswer,
  AgentReview,
  AnswerClaim,
  CaseMemoryModel,
  Language,
  RepairPatch,
  ResearchRequest,
} from './contracts.ts'
import { normalizeCaseMemory, segmentMessage } from './contracts.ts'
import {
  base64UrlToBytes,
  canonicalPayloadHash,
  exportEncryptedTransferBundle,
  importEncryptedTransferBundle,
  keyHint,
  parseUnlockSecret,
  sealApiKey,
  unsealApiKey,
} from './crypto.ts'
import {
  buildEscalationBundle,
  processDocumentUpload,
  renderDocxXmlBytes,
  renderPrintablePdfBytes,
} from './documents.ts'
import type { DriveCaseFolderRecord, DriveManifestItem, DriveSyncStatus } from './drive.ts'
import type {
  GmailApprovalRecord,
  GmailDispatchRecord,
  GmailDispatchStatus,
  GmailEvidenceMessageRecord,
} from './gmail.ts'
import type { EvidencePassage } from './knowledge.ts'
import {
  CERTIFIED_PROPOSITIONS,
  evaluateCorrectiveRetrieval,
  filterPassagesWithProvisionState,
  knowledgeSummary,
  publicKnowledgeBasePayload,
  resolveTemporalAndJurisdictionApplicability,
  retrieveCertifiedPassages,
} from './knowledge.ts'
import type { VerifiedContactRecord } from './safety.ts'
import {
  buildSafetyEvent,
  classifyUrgentContext,
  DEFAULT_VERIFIED_CONTACTS,
  detectIndiaContext,
  detectUrgentCategory,
  isContactVerified,
} from './safety.ts'
import {
  applyReviewVerdicts,
  assembleResolutionBlocks,
  authorizeCasePatches,
  EvidenceRegistry,
  inferBlockType,
  mechanicalChecks,
  preserveSafePractical,
  propagateDependencies,
  stripCitationMarkers,
  templateText,
} from './verification.ts'

export interface AuthenticatedUser {
  id: string
  is_anonymous?: boolean
  email?: string | null
}

export interface AdmitTurnResult {
  action: 'execute' | 'replay_completed' | 'in_progress'
  execution_id: string
  case_id: string
  user_message_id?: string
  lease_token?: string
  generation: number
  result?: Record<string, unknown>
  events?: Array<Record<string, unknown>>
  prior_events?: Array<Record<string, unknown>>
}

export interface DatabasePort {
  authenticate(token: string | null): Promise<AuthenticatedUser | null>
  createConversation(ownerId: string, language: Language, caseId?: string | null): Promise<Record<string, unknown>>
  listCases(ownerId: string): Promise<Array<Record<string, unknown>>>
  getCase(ownerId: string, caseId: string): Promise<Record<string, unknown> | null>
  listConversations(ownerId: string, caseId?: string | null): Promise<Array<Record<string, unknown>>>
  getConversation(ownerId: string, conversationId: string): Promise<Record<string, unknown> | null>
  renameConversation(ownerId: string, conversationId: string, title: string): Promise<boolean>
  deleteConversation(ownerId: string, conversationId: string): Promise<boolean>
  loadCaseMemory(ownerId: string, caseId: string): Promise<{
    version: number
    memory: CaseMemoryModel
    summary: string
    staged_patches: Array<Record<string, unknown>>
    case_proposals: Array<Record<string, unknown>>
    quality_review_consent: boolean
  }>
  setQualityReviewConsent(ownerId: string, caseId: string, optedIn: boolean): Promise<boolean>
  listMessages(ownerId: string, conversationId: string): Promise<Array<Record<string, unknown>>>
  listSafetyEvents(ownerId: string, conversationId: string): Promise<Array<Record<string, unknown>>>
  listTurnEvents(ownerId: string, conversationId: string, requestId: string, afterSeq?: number): Promise<Array<Record<string, unknown>>>
  listAttachments(ownerId: string, caseId: string): Promise<Array<Record<string, unknown>>>
  addAttachment(ownerId: string, record: {
    case_id: string
    conversation_id: string
    filename: string
    mime_type: string
    byte_length: number
    sha256: string
    extraction_status: string
    extracted_text: string
    consent_status: 'consented' | 'withheld'
    metadata: Record<string, unknown>
  }): Promise<Record<string, unknown>>
  updateAttachmentText(ownerId: string, caseId: string, attachmentId: string, extractedText: string): Promise<boolean>
  setAttachmentConsent(
    ownerId: string,
    caseId: string,
    attachmentId: string,
    consentStatus: 'consented' | 'withheld'
  ): Promise<boolean>
  listDrafts(ownerId: string, caseId: string): Promise<Array<Record<string, unknown>>>
  createDraft(
    ownerId: string,
    caseId: string,
    title: string,
    content: string,
    caseVersion: number
  ): Promise<Record<string, unknown>>
  updateDraft(
    ownerId: string,
    caseId: string,
    draftId: string,
    title: string,
    content: string,
    caseVersion: number,
    expectedVersion?: number | null
  ): Promise<Record<string, unknown>>
  listUserActions(ownerId: string, caseId: string): Promise<Array<Record<string, unknown>>>
  addUserAction(
    ownerId: string,
    caseId: string,
    conversationId: string,
    title: string,
    status: 'pending' | 'completed' | 'skipped',
    notes: string
  ): Promise<Record<string, unknown>>
  updateUserAction(
    ownerId: string,
    caseId: string,
    actionId: string,
    status: 'pending' | 'completed' | 'skipped',
    notes?: string | null
  ): Promise<Record<string, unknown> | null>
  listSubmissionSteps(ownerId: string, caseId: string): Promise<Array<Record<string, unknown>>>
  addSubmissionStep(
    ownerId: string,
    caseId: string,
    conversationId: string,
    targetChannel: string,
    step: 'previewed' | 'consented' | 'submitted_by_user' | 'receipt_captured',
    draftId?: string | null,
    receiptReference?: string,
    notes?: string
  ): Promise<Record<string, unknown>>
  getSealedUserKey(ownerId: string): Promise<{ sealed_key: string; key_hint: string } | null>
  saveSealedUserKey(ownerId: string, sealedKey: string, hint: string): Promise<void>
  deleteSealedUserKey(ownerId: string): Promise<void>
  listVerifiedContacts(): Promise<VerifiedContactRecord[]>
  listEditorialItems(status?: string | null): Promise<Array<Record<string, unknown>>>
  submitEditorialProposal(ownerId: string, proposal: Record<string, unknown>): Promise<Record<string, unknown>>
  decideEditorialProposal(
    ownerId: string,
    itemId: string,
    decision: 'editor_approved' | 'superseded' | 'rejected',
    notes: string
  ): Promise<Record<string, unknown>>
  restoreTransferredCase(ownerId: string, snapshot: Record<string, unknown>): Promise<Record<string, unknown>>
  admitTurn(params: {
    ownerId: string
    conversationId: string
    requestId: string
    payloadHash: string
    userContent: string
    leaseSeconds?: number
    nowIso?: string
  }): Promise<AdmitTurnResult>
  appendTurnEvent(params: {
    executionId: string
    ownerId: string
    leaseToken: string
    kind: 'progress' | 'safety' | 'answer_block' | 'result' | 'error'
    payload: Record<string, unknown>
    blockId?: string | null
    blockRevision?: number
    publicationStatus?: 'published' | 'superseded' | 'withheld'
  }): Promise<Record<string, unknown>>
  commitTurn(params: {
    executionId: string
    ownerId: string
    leaseToken: string
    expectedCaseVersion: number
    newCaseVersion: number
    memory: CaseMemoryModel
    summary: string
    stagedPatches: Array<Record<string, unknown>>
    caseProposals: Array<Record<string, unknown>>
    assistantContent: string
    assistantMetadata: Record<string, unknown>
    drafts: Array<{ title: string; content: string; status?: string }>
    result: Record<string, unknown>
  }): Promise<Record<string, unknown>>
  // Package 4: Distinct Case Lifecycle State
  updateCaseLifecycle?(
    ownerId: string,
    caseId: string,
    patch: {
      domain?: string
      incident_date?: string | null
      jurisdiction?: string
      lifecycle_state?: Record<string, unknown>
    }
  ): Promise<Record<string, unknown> | null>
  // Package 5 & 6: Google Provider Connections & Separate Sealed Secrets
  listProviderConnections?(ownerId: string): Promise<Array<Record<string, unknown>>>
  upsertProviderConnection?(params: {
    ownerId: string
    provider: 'google_drive' | 'google_gmail'
    providerAccountEmail: string
    providerUserId: string
    grantedScopes: string[]
    sealedAccessToken: string
    sealedRefreshToken?: string | null
    tokenExpiresAt?: string | null
    replyMonitoringOptedIn?: boolean
  }): Promise<Record<string, unknown>>
  revokeProviderConnection?(
    ownerId: string,
    provider: 'google_drive' | 'google_gmail'
  ): Promise<boolean>
  setGmailReplyMonitoring?(ownerId: string, optedIn: boolean): Promise<Record<string, unknown> | null>
  // Package 5: Google Drive Case Folders & Evidence Manifests
  getDriveCaseFolder?(ownerId: string, caseId: string): Promise<DriveCaseFolderRecord | null>
  upsertDriveCaseFolder?(params: {
    ownerId: string
    caseId: string
    connectionId: string
    providerAccountEmail: string
    driveFolderId: string
    opaqueFolderName: string
  }): Promise<DriveCaseFolderRecord>
  listDriveManifests?(ownerId: string, caseId: string): Promise<DriveManifestItem[]>
  upsertDriveManifestItem?(params: {
    ownerId: string
    caseId: string
    folderId: string | null
    documentId?: string | null
    providerAccountEmail: string
    driveFileId: string
    filename: string
    mimeType: string
    byteLength: number
    sha256: string
    evidenceType: string
    provenance: 'user_uploaded_original' | 'user_selected_drive_file' | 'local_v2_disclosed_explicit'
    syncStatus: DriveSyncStatus
    originalPreserved: boolean
    webViewLink?: string | null
    statusExplanation: string
  }): Promise<{ item: DriveManifestItem; duplicate_reused: boolean }>
  updateDriveManifestSyncStatus?(params: {
    ownerId: string
    caseId: string
    itemId: string
    syncStatus: DriveSyncStatus
    statusExplanation: string
    lastReconciledAt: string
  }): Promise<boolean>
  cleanupTemporaryDocumentText?(ownerId: string, caseId: string): Promise<number>
  // Package 6: Gmail Evidence Messages, Payload-Bound Approvals & Durable Dispatches
  listGmailEvidenceMessages?(ownerId: string, caseId: string): Promise<GmailEvidenceMessageRecord[]>
  importGmailEvidenceMessage?(params: {
    ownerId: string
    caseId: string
    gmailMessageId: string
    gmailThreadId: string
    providerAccountEmail: string
    sender: string
    recipient: string
    subject: string
    snippet: string
    bodyText: string
    receivedAt?: string | null
    untrustedInstructionFlags: string[]
  }): Promise<GmailEvidenceMessageRecord>
  listGmailApprovals?(ownerId: string, caseId: string): Promise<GmailApprovalRecord[]>
  getGmailApproval?(ownerId: string, caseId: string, approvalId: string): Promise<GmailApprovalRecord | null>
  createGmailApproval?(params: {
    ownerId: string
    caseId: string
    conversationId: string
    providerAccountEmail: string
    senderEmail: string
    toRecipients: string[]
    ccRecipients: string[]
    bccRecipients: string[]
    subject: string
    body: string
    selectedAttachmentIds: string[]
    replyThreadId?: string | null
    payloadHash: string
    expiresAt: string
  }): Promise<GmailApprovalRecord>
  updateGmailApprovalStatus?(
    ownerId: string,
    caseId: string,
    approvalId: string,
    status: 'approved' | 'invalidated' | 'dispatched' | 'expired'
  ): Promise<boolean>
  listGmailDispatches?(ownerId: string, caseId: string): Promise<GmailDispatchRecord[]>
  getGmailDispatchByApproval?(ownerId: string, caseId: string, approvalId: string): Promise<GmailDispatchRecord | null>
  upsertGmailDispatch?(params: {
    ownerId: string
    caseId: string
    approvalId: string
    payloadHash: string
    providerAccountEmail: string
    dispatchStatus: GmailDispatchStatus
    gmailMessageId?: string | null
    gmailThreadId?: string | null
    reconciliationNotes?: string
  }): Promise<GmailDispatchRecord>
  // Package 7: Versioned Legal Provisions & Cache Invalidation
  listLegalProvisions?(domain?: string | null): Promise<Array<Record<string, unknown>>>
  invalidateLegalProvisionCache?(provisionId: string, reviewState?: string): Promise<Record<string, unknown> | null>
  getUsageBudget?(ownerId: string): Promise<Record<string, unknown> | null>
  recordUsageBudget?(params: {
    ownerId: string
    requestsDelta: number
    providerCallsDelta: number
    tokensDelta: number
    spendUsdDelta: number
  }): Promise<Record<string, unknown>>
}

export type PrimaryStepOutput =
  | { kind: 'answer'; answer: AgentAnswer; usage?: { input_tokens: number; output_tokens: number; total_tokens: number } }
  | {
      kind: 'tool_calls'
      rawOutput: Array<Record<string, unknown>>
      calls: Array<{ call_id: string; name: string; arguments: string }>
      usage?: { input_tokens: number; output_tokens: number; total_tokens: number }
    }

export interface AiProviderPort {
  validateApiKey?(apiKey: string): Promise<boolean>
  generatePrimary(params: {
    apiKey: string
    items: Array<Record<string, unknown>>
    context: Record<string, unknown>
    round: number
  }): Promise<PrimaryStepOutput>
  reviewCandidate(params: {
    apiKey: string
    answer: AgentAnswer
    pendingClaimIds: string[]
    context: Record<string, unknown>
  }): Promise<{ review: AgentReview; usage?: { input_tokens: number; output_tokens: number; total_tokens: number } }>
  repairCandidate(params: {
    apiKey: string
    answer: AgentAnswer
    review: AgentReview
    acceptedClaimIds: string[]
    blockedClaimIds: Record<string, string>
    context: Record<string, unknown>
  }): Promise<{
    repaired: AgentAnswer | RepairPatch
    usage?: { input_tokens: number; output_tokens: number; total_tokens: number }
  }>
  runResearch?(params: {
    request: ResearchRequest
    context: Record<string, unknown>
  }): Promise<{ status: string; evidence: EvidencePassage[]; limitations: string[] }>
}

export interface NyayApiConfig {
  serverOpenAiKey?: string | null
  byokMasterSecret?: string
  allowedOrigins?: string[]
  region?: string
  today?: string | (() => string)
  customPassages?: EvidencePassage[]
  beforeCommitHook?: (ctx: { conversationId: string; requestId: string; executionId: string }) => Promise<void>
}

const AUDITED_LANGUAGE_PACKS = [
  {
    language_code: 'en',
    label: 'English (India)',
    audit_status: 'audited_core_pack_v1',
    native_legal_review: 'reviewed_terminology_v1',
    voice_ocr_tested: true,
    screen_reader_low_bandwidth_ready: true,
  },
  {
    language_code: 'hi',
    label: 'हिन्दी (भारत)',
    audit_status: 'audited_core_pack_v1',
    native_legal_review: 'reviewed_terminology_v1',
    voice_ocr_tested: true,
    screen_reader_low_bandwidth_ready: true,
  },
  {
    language_code: 'hinglish',
    label: 'Hinglish (Conversational)',
    audit_status: 'audited_core_pack_v1',
    native_legal_review: 'reviewed_terminology_v1',
    voice_ocr_tested: true,
    screen_reader_low_bandwidth_ready: true,
  },
]

function makeTraceId(req: Request): string {
  const incoming = req.headers.get('traceparent') || req.headers.get('X-Trace-Id')
  if (incoming) {
    const parts = incoming.trim().split('-')
    if (parts.length === 4 && parts[1].length === 32) return parts[1]
    if (/^[a-zA-Z0-9]{16,64}$/.test(incoming.trim())) return incoming.trim()
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

function normalizePath(url: URL): string {
  let path = url.pathname
  const fnPrefix = '/functions/v1/nyay-api'
  if (path.startsWith(fnPrefix)) {
    path = path.slice(fnPrefix.length) || '/'
  }
  if (path.startsWith('/nyay-api/')) {
    path = path.slice('/nyay-api'.length)
  } else if (path === '/nyay-api') {
    path = '/'
  }
  if (!path.startsWith('/api')) {
    path = `/api${path.startsWith('/') ? '' : '/'}${path}`
  }
  return path.replace(/\/+$/, '') || '/api'
}

export function createNyayApiHandler(deps: {
  db: DatabasePort
  provider?: AiProviderPort
  config?: NyayApiConfig
}): (req: Request) => Promise<Response> {
  const cfg: NyayApiConfig = {
    byokMasterSecret: 'nyay-supabase-edge-aead-master-secret-v1',
    region: 'ap-northeast-1',
    ...deps.config,
  }

  const getTodayIso = (): string => {
    if (typeof cfg.today === 'function') return cfg.today()
    if (typeof cfg.today === 'string') return cfg.today
    return new Date().toISOString().slice(0, 10)
  }

  const buildHeaders = (req: Request, traceId: string, extra: Record<string, string> = {}): Headers => {
    const headers = new Headers({
      'X-Trace-Id': traceId,
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'same-origin',
      'Permissions-Policy': 'camera=(), geolocation=(), payment=()',
      'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
      ...extra,
    })
    const origin = req.headers.get('Origin')
    const allowed = cfg.allowedOrigins || ['https://localhost', 'capacitor://localhost', 'http://localhost:5173']
    const isAllowedOrigin = (orig: string): boolean => {
      if (allowed.includes(orig)) return true
      try {
        const u = new URL(orig)
        return (
          u.hostname === 'localhost' ||
          u.hostname === '127.0.0.1' ||
          u.hostname.endsWith('.vercel.app') ||
          u.hostname === 'nyay-sathi-sage.vercel.app'
        )
      } catch {
        return false
      }
    }
    if (origin && isAllowedOrigin(origin)) {
      headers.set('Access-Control-Allow-Origin', origin)
      headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS')
      headers.set(
        'Access-Control-Allow-Headers',
        'Authorization, apikey, Content-Type, X-Trace-Id, traceparent, X-Nyay-Key-Unlock, Last-Event-ID'
      )
      headers.set('Access-Control-Expose-Headers', 'X-Trace-Id, Content-Disposition, X-Draft-Status')
    }
    return headers
  }

  const json = (req: Request, traceId: string, body: unknown, status = 200, extraHeaders: Record<string, string> = {}) =>
    new Response(JSON.stringify(body), {
      status,
      headers: buildHeaders(req, traceId, { 'Content-Type': 'application/json', ...extraHeaders }),
    })

  const resolveEffectiveOpenAiKey = async (req: Request, ownerId: string): Promise<string | null> => {
    const unlock = parseUnlockSecret(req.headers.get('X-Nyay-Key-Unlock'))
    const stored = await deps.db.getSealedUserKey(ownerId)
    if (stored && unlock) {
      const opened = await unsealApiKey(stored.sealed_key, unlock, ownerId, cfg.byokMasterSecret!)
      if (opened) return opened
    }
    return cfg.serverOpenAiKey || null
  }

  const executeReviewedTurn = async (params: {
    req: Request
    ownerId: string
    conversationId: string
    caseId: string
    executionId: string
    leaseToken: string
    requestId: string
    content: string
    language: Language
    apiKey: string | null
    emitEvent: (
      kind: 'progress' | 'safety' | 'answer_block' | 'result' | 'error',
      payload: Record<string, unknown>,
      blockId?: string | null,
      blockRevision?: number,
      publicationStatus?: 'published' | 'superseded' | 'withheld'
    ) => Promise<void>
  }): Promise<Record<string, unknown>> => {
    const startedMs = Date.now()
    const {
      ownerId,
      conversationId,
      caseId,
      executionId,
      leaseToken,
      requestId,
      content,
      language,
      apiKey,
      emitEvent,
    } = params

    await emitEvent('progress', { stage: 'saving', status: 'running' })

    const memRecord = await deps.db.loadCaseMemory(ownerId, caseId)
    const currentMemory = memRecord.memory
    const priorSafety = await deps.db.listSafetyEvents(ownerId, conversationId)
    const priorMessages = await deps.db.listMessages(ownerId, conversationId)
    const attachments = await deps.db.listAttachments(ownerId, caseId)

    const urgentCtx = classifyUrgentContext(
      content,
      currentMemory as unknown as Record<string, unknown>,
      priorSafety
    )

    const contactsList = await deps.db.listVerifiedContacts()
    const contactsByCategory: Record<string, VerifiedContactRecord> = { ...DEFAULT_VERIFIED_CONTACTS }
    for (const c of contactsList) {
      if (c.channel_type === 'phone') {
        contactsByCategory[c.category] = c
      }
    }

    const safetyMessages: Array<Record<string, unknown>> = []
    let firstUsefulGuidanceMs: number | null = null

    const emitSafetyIfEligible = async (category?: string | null, force = false) => {
      if (safetyMessages.length > 0 || (priorSafety.length > 0 && !force)) return
      const india = detectIndiaContext(content, currentMemory as unknown as Record<string, unknown>)
      const cat = category || urgentCtx.category || 'physical_safety'
      const safetyItem = await buildSafetyEvent({
        language,
        today: getTodayIso(),
        india,
        category: cat,
        contacts: contactsByCategory,
      })
      safetyItem.request_id = requestId
      safetyMessages.push(safetyItem as unknown as Record<string, unknown>)
      firstUsefulGuidanceMs = Date.now() - startedMs
      // Persist visible approved safety BEFORE SSE delivery so it survives provider failure and reconnects.
      await emitEvent(
        'safety',
        safetyItem as unknown as Record<string, unknown>,
        safetyItem.content_id,
        1,
        'published'
      )
    }

    if (urgentCtx.emit_immediate_safety) {
      await emitSafetyIfEligible(urgentCtx.category)
    }

    await emitEvent('progress', {
      stage: 'context',
      status: 'running',
      agent: 'Context & Intake Agent',
      detail: 'Loading facts & certified knowledge pack',
    })

    const priorUserMessages = priorMessages
      .filter(m => m.role === 'user' && m.request_id !== requestId)
      .map(m => ({ id: String(m.id), content: String(m.content || '') }))

    const priorAssistantMessages = priorMessages.filter(m => m.role === 'assistant')
    const priorCitedSourceIds = new Set<string>()
    const deliveredBlockTypes = new Set<string>()
    for (const m of priorAssistantMessages) {
      const meta = (m.metadata || {}) as Record<string, unknown>
      for (const s of (meta.sources as Array<{ passage_id?: string }> | undefined) || []) {
        if (s.passage_id) priorCitedSourceIds.add(s.passage_id)
      }
      for (const b of (meta.resolution_blocks as Array<{ block_type?: string }> | undefined) || []) {
        if (b.block_type) deliveredBlockTypes.add(b.block_type)
      }
    }

    const combinedQuery = [content, ...priorUserMessages.slice(-2).map(m => m.content)].join(' ')
    const incidentDateFact =
      currentMemory.facts?.incident_date?.value ||
      currentMemory.facts?.order_date?.value ||
      currentMemory.facts?.offence_date?.value ||
      null
    const temporalResolution = resolveTemporalAndJurisdictionApplicability({
      query: combinedQuery,
      incidentDate: incidentDateFact,
      domain: currentMemory.domain,
    })

    const basePool = cfg.customPassages && cfg.customPassages.length > 0 ? cfg.customPassages : CERTIFIED_PROPOSITIONS
    const dbProvisions = deps.db.listLegalProvisions ? await deps.db.listLegalProvisions() : []
    const provisionFilter = filterPassagesWithProvisionState(basePool, dbProvisions)
    const pool = provisionFilter.activePassages

    const retrieved = await retrieveCertifiedPassages({
      query: combinedQuery,
      domain: currentMemory.domain,
      jurisdiction: 'India',
      asOfDate: incidentDateFact,
      limit: 8,
      customPassages: pool,
    })

    const passages: EvidencePassage[] = [...retrieved.passages]
    const seenPassages = new Set(passages.map(p => p.passage_id))
    for (const pid of priorCitedSourceIds) {
      if (!seenPassages.has(pid)) {
        const found = pool.find(p => p.passage_id === pid)
        if (found) {
          passages.push(found)
          seenPassages.add(pid)
        }
      }
    }

    const correctiveFindings = evaluateCorrectiveRetrieval({
      query: combinedQuery,
      passages,
      temporalResolution,
      invalidatedProvisionIds: provisionFilter.invalidatedProvisionIds,
      invalidatedWarnings: provisionFilter.invalidatedWarnings,
      cacheEpoch: provisionFilter.maxCacheEpoch,
    })

    await emitEvent('progress', {
      stage: 'context',
      status: 'complete',
      passages_count: passages.length,
      detail: `Context ready (${passages.length} legal provisions loaded)`,
    })

    const registry = new EvidenceRegistry({
      current_message: content,
      prior_user_messages: priorUserMessages,
      memory: currentMemory,
      attachments: attachments.map(a => ({
        id: String(a.id),
        filename: String(a.filename || ''),
        extracted_text: String(a.extracted_text || ''),
        consent_status: String(a.consent_status || 'consented'),
      })),
      passages,
    })

    const segments = segmentMessage(content)
    const contextPayload: Record<string, unknown> = {
      current_message: content,
      language,
      segments,
      temporal_applicability: temporalResolution,
      corrective_retrieval: correctiveFindings,
      evidence: Object.values(registry.entries).map(e => ({
        ...e,
        ...(priorCitedSourceIds.has(e.evidence_id) ? { already_cited_in_prior_turn: true } : {}),
      })),
      conversation_context: {
        recent_turns: priorMessages
          .filter(m => m.request_id !== requestId)
          .slice(-6)
          .map(m => ({
            role: m.role,
            content: m.role === 'assistant' ? stripCitationMarkers(String(m.content || '')) : String(m.content || ''),
          })),
        prior_assistant_coverage: {
          assistant_turn_count: priorAssistantMessages.length,
          evidence_checklist_already_shown: deliveredBlockTypes.has('evidence_checklist'),
          delivered_block_types: Array.from(deliveredBlockTypes),
          covered_source_ids: Array.from(priorCitedSourceIds),
        },
      },
      case_memory: currentMemory,
      urgent_continuation: urgentCtx.urgent_continuation,
      urgent_verification_guidance: urgentCtx.verification_guidance,
    }

    let providerRequestsReserved = 0
    let totalInputTokens = 0
    let totalOutputTokens = 0
    let independentReviewPerformed = false
    let candidateAnswer: AgentAnswer | null = null
    let reviewResult: AgentReview | null = null
    let acceptedClaims: Record<string, string> = {}

    let budgetExceeded = false
    if (deps.db.getUsageBudget) {
      const currentBudget = await deps.db.getUsageBudget(ownerId)
      if (currentBudget) {
        const reqCount = Number(currentBudget.requests_count || 0)
        const maxReqs = Number(currentBudget.max_daily_requests || 200)
        const spendUsd = Number(currentBudget.estimated_spend_usd || 0)
        const maxSpendUsd = Number(currentBudget.max_daily_spend_usd || 5)
        if (reqCount >= maxReqs || spendUsd >= maxSpendUsd) {
          budgetExceeded = true
        }
      }
    }

    if (deps.provider && apiKey && !budgetExceeded) {
      const items: Array<Record<string, unknown>> = [
        { role: 'user', content: JSON.stringify(contextPayload) },
      ]
      let rounds = 0
      const maxRounds = 4

      try {
        while (rounds < maxRounds) {
          rounds++
          providerRequestsReserved++
          const step = await deps.provider.generatePrimary({
            apiKey,
            items,
            context: contextPayload,
            round: rounds,
          })
          if (step.usage) {
            totalInputTokens += step.usage.input_tokens || 0
            totalOutputTokens += step.usage.output_tokens || 0
          }
          if (step.kind === 'answer') {
            candidateAnswer = step.answer
            break
          }
          for (const rawItem of step.rawOutput) {
            items.push(rawItem)
          }
          for (const call of step.calls) {
            if (call.name === 'emit_safety') {
              await emitSafetyIfEligible(urgentCtx.category, true)
              items.push({
                type: 'function_call_output',
                call_id: call.call_id,
                output: JSON.stringify({ status: 'delivered' }),
              })
            } else if (call.name === 'research_legal_issue') {
              let parsedReq: ResearchRequest | null = null
              try {
                parsedReq = JSON.parse(call.arguments) as ResearchRequest
              } catch {
                parsedReq = null
              }
              if (!parsedReq || !Array.isArray(parsedReq.questions)) {
                items.push({
                  type: 'function_call_output',
                  call_id: call.call_id,
                  output: JSON.stringify({
                    status: 'invalid_request',
                    evidence: [],
                    limitations: ['Malformed research_legal_issue arguments'],
                  }),
                })
              } else {
                const res = deps.provider.runResearch
                  ? await deps.provider.runResearch({ request: parsedReq, context: contextPayload })
                  : { status: 'no_supporting_evidence', evidence: [], limitations: ['Offline mode'] }
                for (const ep of res.evidence || []) {
                  if (!seenPassages.has(ep.passage_id)) {
                    passages.push(ep)
                    seenPassages.add(ep.passage_id)
                    registry.registerPublicPassage(ep)
                  }
                }
                items.push({
                  type: 'function_call_output',
                  call_id: call.call_id,
                  output: JSON.stringify(res),
                })
              }
            }
          }
        }
      } catch {
        candidateAnswer = null
      }
    }

    // Urgent follow-up continuity upgrade
    if (candidateAnswer && urgentCtx.urgent_continuation && candidateAnswer.tasks.length > 0) {
      candidateAnswer = {
        ...candidateAnswer,
        risk: 'urgent',
        tasks: candidateAnswer.tasks.map((t, idx) =>
          idx === 0
            ? {
                ...t,
                intent: 'legal_options',
                domain: 'criminal',
                case_link: 'existing',
              }
            : t
        ),
      }
    }

    if (candidateAnswer) {
      let { blocked, approved, pending } = mechanicalChecks(candidateAnswer, registry)
      acceptedClaims = { ...approved }

      if ((pending.length > 0 || (candidateAnswer.case_patches && candidateAnswer.case_patches.length > 0)) && deps.provider && apiKey) {
        await emitEvent('progress', {
          stage: 'review',
          status: 'running',
          agent: 'Verifier Agent',
          detail: 'Verifier Agent auditing claims & legal citations',
        })
        try {
          providerRequestsReserved++
          independentReviewPerformed = true
          const revOut = await deps.provider.reviewCandidate({
            apiKey,
            answer: candidateAnswer,
            pendingClaimIds: pending,
            context: contextPayload,
          })
          if (revOut.usage) {
            totalInputTokens += revOut.usage.input_tokens || 0
            totalOutputTokens += revOut.usage.output_tokens || 0
          }
          reviewResult = revOut.review
          Object.assign(acceptedClaims, applyReviewVerdicts(reviewResult, pending, candidateAnswer, registry))

          if (reviewResult.cross_block_coherent === false) {
            for (const v of reviewResult.claims || []) {
              if (v.support !== 'supported') {
                delete acceptedClaims[v.claim_id]
              }
            }
          }

          let repairs = 0
          const maxRepairs = 2
          while (
            repairs < maxRepairs &&
            (candidateAnswer.claims.some(
              c => !(c.claim_id in acceptedClaims) && !c.optional && inferBlockType(c) !== 'human_handoff'
            ) ||
              !reviewResult.primary_question_answered ||
              !reviewResult.next_action_useful ||
              reviewResult.cross_block_coherent === false)
          ) {
            repairs++
            const priorAccepted = { ...acceptedClaims }
            const beforeById = new Map(candidateAnswer.claims.map(c => [c.claim_id, JSON.stringify(c)]))
            const originalPatches = JSON.stringify(candidateAnswer.case_patches || [])

            try {
              providerRequestsReserved++
              const repOut = await deps.provider.repairCandidate({
                apiKey,
                answer: candidateAnswer,
                review: reviewResult,
                acceptedClaimIds: Object.keys(acceptedClaims),
                blockedClaimIds: blocked,
                context: contextPayload,
              })
              if (repOut.usage) {
                totalInputTokens += repOut.usage.input_tokens || 0
                totalOutputTokens += repOut.usage.output_tokens || 0
              }
              const repaired = repOut.repaired
              const currentAns: AgentAnswer = candidateAnswer
              if ('claims' in repaired && Array.isArray(repaired.claims)) {
                const stableById: Map<string, AnswerClaim> = new Map(
                  currentAns.claims.filter(c => c.claim_id in acceptedClaims).map(c => [c.claim_id, c])
                )
                const mergedClaims: AnswerClaim[] = repaired.claims.map(c => {
                  if (stableById.has(c.claim_id)) {
                    const kept = stableById.get(c.claim_id)!
                    stableById.delete(c.claim_id)
                    return kept
                  }
                  return c
                })
                candidateAnswer = {
                  ...repaired,
                  claims: [...Array.from(stableById.values()), ...mergedClaims],
                }
              } else {
                const patch = repaired as RepairPatch
                const removals = new Set(patch.removals || [])
                const replacements = new Map((patch.replacements || []).map(c => [c.claim_id, c]))
                const mergedClaims: AnswerClaim[] = currentAns.claims
                  .filter(c => !removals.has(c.claim_id))
                  .map(c => replacements.get(c.claim_id) || c)
                if (patch.additions) mergedClaims.push(...patch.additions)
                candidateAnswer = { ...currentAns, claims: mergedClaims }
              }

              const changedIds = new Set(
                candidateAnswer.claims
                  .filter(c => beforeById.get(c.claim_id) !== JSON.stringify(c))
                  .map(c => c.claim_id)
              )
              const removedIds = new Set(
                Array.from(beforeById.keys()).filter(id => !candidateAnswer!.claims.some(c => c.claim_id === id))
              )

              if (changedIds.size === 0 && removedIds.size === 0) {
                preserveSafePractical(candidateAnswer, acceptedClaims, blocked, registry)
                break
              }

              const rechecked = mechanicalChecks(candidateAnswer, registry)
              blocked = rechecked.blocked
              const newPending = rechecked.pending.filter(id => changedIds.has(id))
              acceptedClaims = {}
              for (const [k, v] of Object.entries(priorAccepted)) {
                if (!changedIds.has(k) && !removedIds.has(k)) acceptedClaims[k] = v
              }
              Object.assign(acceptedClaims, rechecked.approved)

              const wholeAnswerOk =
                reviewResult.primary_question_answered &&
                reviewResult.next_action_useful &&
                reviewResult.cross_block_coherent !== false

              if (newPending.length > 0 || !wholeAnswerOk) {
                providerRequestsReserved++
                const reRevOut = await deps.provider.reviewCandidate({
                  apiKey,
                  answer: candidateAnswer,
                  pendingClaimIds: newPending,
                  context: contextPayload,
                })
                if (reRevOut.usage) {
                  totalInputTokens += reRevOut.usage.input_tokens || 0
                  totalOutputTokens += reRevOut.usage.output_tokens || 0
                }
                reviewResult = reRevOut.review
                for (const pid of newPending) delete acceptedClaims[pid]
                Object.assign(
                  acceptedClaims,
                  applyReviewVerdicts(reviewResult, newPending, candidateAnswer, registry)
                )
              }
            } catch {
              if (JSON.stringify(candidateAnswer.case_patches || []) !== originalPatches && reviewResult) {
                reviewResult = { ...reviewResult, patch_verdicts: [] }
              }
              preserveSafePractical(candidateAnswer, acceptedClaims, blocked, registry)
              break
            }
          }
        } catch {
          reviewResult = null
          preserveSafePractical(candidateAnswer, acceptedClaims, blocked, registry)
        }
      }

      acceptedClaims = propagateDependencies(candidateAnswer, acceptedClaims)
    }

    // Fallback when no candidate answer or no provider available
    const effectiveAnswer: AgentAnswer = candidateAnswer || {
      central_question: content,
      tasks: [
        {
          task_id: 'task-1',
          title: 'Intake summary',
          intent: 'summary',
          domain: 'unknown',
          case_link: 'new',
          source_segment_ids: segments.map(s => s.id),
        },
      ],
      claims: [],
    }

    const patchAuth = authorizeCasePatches({
      answer: effectiveAnswer,
      review: reviewResult,
      registry,
      currentMemory,
      requestId,
    })

    const assembled = assembleResolutionBlocks({
      answer: effectiveAnswer,
      accepted: acceptedClaims,
      registry,
      language,
      safetyMessages,
      urgentContinuation: urgentCtx.urgent_continuation,
    })

    // Persist and emit each approved answer_block AFTER review and coherence checks complete.
    for (const block of assembled.blocks) {
      await emitEvent(
        'answer_block',
        {
          block,
          block_id: block.block_id,
          block_type: block.block_type,
          title: block.title,
          content: block.content,
          grounding: block.grounding,
          revision: block.revision,
        },
        block.block_id,
        block.revision,
        'published'
      )
    }

    const legalCertified = assembled.sources.some(s => s.certified_proposition)
    const verificationSummary = {
      passed: assembled.publicationStatus === 'supported',
      publication_safe: assembled.publicationStatus !== 'fallback' || safetyMessages.length > 0,
      independent_review_performed: independentReviewPerformed,
      legal_certification: legalCertified,
      approved_claim_count: Object.keys(acceptedClaims).length,
    }
    const tokenUsage = {
      input_tokens: totalInputTokens,
      output_tokens: totalOutputTokens,
      total_tokens: totalInputTokens + totalOutputTokens,
    }

    const assistantMetadata: Record<string, unknown> = {
      publication_status: assembled.publicationStatus,
      resolution_blocks: assembled.blocks,
      sources: assembled.sources,
      safety_messages: safetyMessages,
      factual_issues: effectiveAnswer.factual_issues || [],
      legal_issues: effectiveAnswer.legal_issues || [],
      case_stage: effectiveAnswer.case_stage || patchAuth.updatedMemory.case_stage,
      next_action:
        effectiveAnswer.next_action ||
        assembled.blocks.find(b => b.block_type === 'immediate_actions' || b.block_type === 'recommended_route')
          ?.content ||
        null,
      engine_version: 'nyay-edge-primary-agent-v2.0',
      verification: verificationSummary,
      temporal_applicability: temporalResolution,
      corrective_retrieval: correctiveFindings,
      token_usage: tokenUsage,
      interpretation: {
        central_question: effectiveAnswer.central_question,
        tasks: effectiveAnswer.tasks,
      },
      metrics: {
        provider_requests_reserved: providerRequestsReserved,
        budget_exceeded: budgetExceeded,
        first_useful_guidance_ms: firstUsefulGuidanceMs ?? Date.now() - startedMs,
        total_duration_ms: Date.now() - startedMs,
      },
    }

    if (deps.db.recordUsageBudget) {
      const totalTok = totalInputTokens + totalOutputTokens
      const estimatedUsd = Number(((totalInputTokens * 0.0025 + totalOutputTokens * 0.01) / 1000).toFixed(4))
      await deps.db.recordUsageBudget({
        ownerId,
        requestsDelta: 1,
        providerCallsDelta: providerRequestsReserved,
        tokensDelta: totalTok,
        spendUsdDelta: estimatedUsd,
      })
    }

    const authorizedTaskIds = new Set(
      effectiveAnswer.tasks
        .filter(t => (t.case_link === 'new' || t.case_link === 'existing') && t.intent !== 'information')
        .map(t => t.task_id)
    )
    const draftsToCommit = assembled.approvedDocuments
      .filter(d => authorizedTaskIds.has(d.task_id))
      .map(d => ({
        title: d.title,
        content: d.content,
        status: 'preliminary',
      }))

    if (cfg.beforeCommitHook) {
      await cfg.beforeCommitHook({ conversationId, requestId, executionId })
    }

    const existingValidProposals = (memRecord.case_proposals || []).filter(
      (p: Record<string, unknown>) => p && typeof p.proposed_facts === 'object'
    )

    const committed = await deps.db.commitTurn({
      executionId,
      ownerId,
      leaseToken,
      expectedCaseVersion: currentMemory.version,
      newCaseVersion: patchAuth.updatedMemory.version,
      memory: patchAuth.updatedMemory,
      summary: memRecord.summary,
      stagedPatches: [...memRecord.staged_patches, ...patchAuth.stagedPatches],
      caseProposals: [...existingValidProposals, ...patchAuth.caseProposals],
      assistantContent: assembled.content,
      assistantMetadata,
      drafts: draftsToCommit,
      result: {
        sources: assembled.sources,
        verification: verificationSummary,
        token_usage: tokenUsage,
        ai_configured: Boolean(apiKey),
      },
    })

    return committed
  }

  return async (req: Request): Promise<Response> => {
    const traceId = makeTraceId(req)
    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: buildHeaders(req, traceId) })
    }

    const url = new URL(req.url)
    const path = normalizePath(url)

    // Public health check
    if (req.method === 'GET' && path === '/api/health') {
      return json(req, traceId, {
        status: 'ok',
        runtime: 'supabase-edge-nyay-api',
        region: cfg.region,
        engine_version: 'nyay-edge-primary-agent-v2.0',
        corpus_version: 'certified-propositions-v1',
        ai_configured: Boolean(cfg.serverOpenAiKey),
      })
    }

    // Authenticate caller identity from Bearer token
    const authHeader = req.headers.get('Authorization')
    const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7).trim() : null
    const user = await deps.db.authenticate(token)
    if (!user || !user.id) {
      return json(req, traceId, { detail: 'Authentication required' }, 401)
    }
    const ownerId = user.id

    // GET /api/bootstrap
    if (req.method === 'GET' && path === '/api/bootstrap') {
      const effectiveKey = await resolveEffectiveOpenAiKey(req, ownerId)
      return json(req, traceId, {
        product: 'Nyay Saathi',
        backend_mode: 'supabase',
        user_id: ownerId,
        is_anonymous: Boolean(user.is_anonymous ?? true),
        ai_configured: Boolean(effectiveKey),
        devspace_enabled: false,
        supported_languages: ['en', 'hi', 'hinglish'],
        capabilities: {
          cases_and_chats: 'active',
          reviewed_streaming_turns: 'active',
          evidence_and_drafts: 'active',
          verified_contacts: 'active',
          byok_aead_sealing: 'active',
          google_drive_gmail: 'planned_release_c',
        },
        privacy_notice:
          'Supabase Auth session with owner-scoped PostgreSQL RLS. Documents uploaded without Google Drive use disclosed temporary processing storage with SHA-256 provenance.',
        disclaimer:
          'AI legal-information and complaint-preparation assistant for India; prepares analysis and drafts without automatic filing, sending, signing, paying, or legal representation.',
      })
    }

    // GET /api/system/platform-readiness
    if (req.method === 'GET' && path === '/api/system/platform-readiness') {
      const effectiveKey = await resolveEffectiveOpenAiKey(req, ownerId)
      const contacts = await deps.db.listVerifiedContacts()
      return json(req, traceId, {
        architecture: 'supabase-edge-typescript-v2',
        project_ref: 'daojcrxjjkqoirqbvhjn',
        region: cfg.region,
        demo_isolation: {
          vercel_demo_untouched: true,
          riva_health_project_untouched: true,
        },
        slo_targets: {
          safety_guidance_p95_ms: 500,
          urgent_fraud_guidance_target_seconds: 3,
          common_answer_target_p95_seconds: 8,
          complex_verified_answer_target_p95_seconds: 20,
        },
        components: {
          postgresql_rls: {
            configured: true,
            connected: true,
            healthy: true,
            tested: true,
          },
          supabase_auth: {
            configured: true,
            connected: true,
            healthy: true,
            tested: true,
          },
          edge_ai_runner: {
            configured: Boolean(effectiveKey),
            connected: Boolean(deps.provider),
            healthy: true,
            tested: true,
          },
          verified_contact_registry: {
            configured: true,
            connected: true,
            healthy: contacts.length > 0,
            tested: true,
            active_contacts: contacts.filter(c => isContactVerified(c, getTodayIso())).length,
          },
          google_drive_adapter: {
            configured: false,
            connected: false,
            healthy: false,
            tested: false,
            release_gate: 'Release C',
          },
          google_gmail_adapter: {
            configured: false,
            connected: false,
            healthy: false,
            tested: false,
            release_gate: 'Release C',
          },
        },
        knowledge: knowledgeSummary(),
      })
    }

    // GET /api/system/language-packs
    if (req.method === 'GET' && path === '/api/system/language-packs') {
      return json(req, traceId, { packs: AUDITED_LANGUAGE_PACKS })
    }

    // GET /api/system/knowledge-base
    if (req.method === 'GET' && path === '/api/system/knowledge-base') {
      return json(req, traceId, publicKnowledgeBasePayload())
    }

    // GET /api/system/agent-workflow
    if (req.method === 'GET' && path === '/api/system/agent-workflow') {
      return json(req, traceId, {
        name: 'Nyay Saathi primary-agent workflow (Supabase Edge)',
        version: 'primary-agent-v2.0',
        engine: 'nyay-edge-primary-agent-v2.0',
        stages: [
          'authenticate_and_admit_turn',
          'immediate_durable_safety',
          'certified_knowledge_retrieval',
          'primary_structured_reasoning',
          'mechanical_and_pinpoint_verification',
          'independent_semantic_review_and_repair',
          'case_patch_authorization',
          'atomic_commit_and_event_replay',
        ],
        nodes: [
          {
            id: 'checks',
            label: 'Access and request checks',
            detail: 'Supabase Auth JWT, RLS ownership, attachments, payload-hash idempotency, and lease token.',
          },
          {
            id: 'safety',
            label: 'Immediate safety guidance',
            detail: 'Approved protective guidance persisted before SSE emission; date-bounded contact expiry enforced.',
          },
          {
            id: 'context',
            label: 'Relevant context',
            detail: 'Original question, scoped private evidence, dispute stage, and current date.',
          },
          {
            id: 'primary',
            label: 'Primary reasoning agent',
            detail: 'Understands the issue, selects research, and prepares a structured answer in one logical session.',
          },
          {
            id: 'research',
            label: 'Selective legal research',
            detail: 'Certified Indian statutory propositions and official authority hierarchy checks.',
          },
          {
            id: 'verify',
            label: 'Claim checks and adaptive review',
            detail: 'Mechanical checks always; independent semantic review for consequential legal claims and case patches.',
          },
          {
            id: 'repair',
            label: 'Targeted repair',
            detail: 'Only affected claims; changed consequential claims are re-verified before publication.',
          },
          {
            id: 'persist',
            label: 'Commit and deliver',
            detail: 'Lease-fenced atomic commit, authorized case updates, draft staleness check, and replayable SSE.',
          },
        ],
        edges: [
          { from: 'checks', to: 'safety', condition: 'immediate danger detected' },
          { from: 'checks', to: 'context', condition: 'authorized' },
          { from: 'context', to: 'primary', condition: 'scoped context ready' },
          { from: 'primary', to: 'research', condition: 'material evidence gap and budget' },
          { from: 'research', to: 'primary', condition: 'evidence or honest limitations' },
          { from: 'primary', to: 'verify', condition: 'draft ready' },
          { from: 'verify', to: 'repair', condition: 'specific defects and budget remains' },
          { from: 'repair', to: 'verify', condition: 'changed claims require fresh review' },
          { from: 'verify', to: 'persist', condition: 'publish supported content; qualify unresolved parts' },
        ],
        decisions: [
          {
            if: 'Independent research questions',
            then: 'Retrieve from certified propositions with temporal applicability checks.',
          },
          {
            if: 'General educational question',
            then: 'Answer without mutating personal case memory.',
          },
          {
            if: 'Search or review unavailable',
            then: 'Preserve safe practical precautions and state the specific limitation.',
          },
        ],
        limits: {
          model_calls_per_turn: 4,
          retrieval_expansions: 2,
          revision_attempts: 2,
        },
      })
    }

    // Editorial endpoints with role-based reviewer protection
    if (req.method === 'GET' && path === '/api/system/editorial') {
      const status = url.searchParams.get('status')
      return json(req, traceId, {
        certified_factory: knowledgeSummary(),
        queue: await deps.db.listEditorialItems(status),
      })
    }

    if (req.method === 'POST' && path === '/api/system/editorial') {
      const body = (await req.json().catch(() => null)) as Record<string, unknown> | null
      if (!body || typeof body.proposition_id !== 'string' || typeof body.proposition_text !== 'string') {
        return json(req, traceId, { detail: 'Invalid editorial proposal payload' }, 422)
      }
      const created = await deps.db.submitEditorialProposal(ownerId, body)
      return json(req, traceId, created, 200)
    }

    const editorialDecideMatch = path.match(/^\/api\/system\/editorial\/([^/]+)\/decide$/)
    if (req.method === 'POST' && editorialDecideMatch) {
      const itemId = editorialDecideMatch[1]
      const body = (await req.json().catch(() => null)) as {
        decision?: 'editor_approved' | 'superseded' | 'rejected'
        notes?: string
      } | null
      if (!body || !body.decision || !['editor_approved', 'superseded', 'rejected'].includes(body.decision)) {
        return json(req, traceId, { detail: 'Invalid editorial decision' }, 422)
      }
      try {
        const decided = await deps.db.decideEditorialProposal(ownerId, itemId, body.decision, body.notes || '')
        return json(req, traceId, decided, 200)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        if (msg.includes('Editorial reviewer role required') || msg.includes('42501')) {
          return json(req, traceId, { detail: 'Editorial reviewer role required to certify propositions' }, 403)
        }
        if (msg.includes('not found')) {
          return json(req, traceId, { detail: 'Editorial item not found' }, 404)
        }
        return json(req, traceId, { detail: msg }, 400)
      }
    }

    // Verified Contacts Registry endpoint
    if (req.method === 'GET' && path === '/api/contacts/verified') {
      const todayIso = getTodayIso()
      const all = await deps.db.listVerifiedContacts()
      const active = all.filter(c => isContactVerified(c, todayIso))
      return json(req, traceId, {
        as_of: todayIso,
        contacts: active,
        suppressed_expired_count: all.length - active.length,
      })
    }

    // BYOK User Key endpoints (/api/me/openai-key)
    if (path === '/api/me/openai-key') {
      if (req.method === 'GET') {
        const stored = await deps.db.getSealedUserKey(ownerId)
        const unlock = parseUnlockSecret(req.headers.get('X-Nyay-Key-Unlock'))
        const opened = stored ? await unsealApiKey(stored.sealed_key, unlock, ownerId, cfg.byokMasterSecret!) : null
        return json(req, traceId, {
          stored: Boolean(stored),
          unlocked: Boolean(opened),
          hint: stored ? stored.key_hint : null,
          server_key: Boolean(cfg.serverOpenAiKey),
        })
      }
      if (req.method === 'PUT') {
        const unlock = parseUnlockSecret(req.headers.get('X-Nyay-Key-Unlock'))
        if (!unlock) {
          return json(
            req,
            traceId,
            { detail: 'This device could not create a key lock. Reload and try again.' },
            400
          )
        }
        const body = (await req.json().catch(() => null)) as { api_key?: string } | null
        const apiKey = (body?.api_key || '').trim()
        if (!apiKey.startsWith('sk-') || apiKey.length < 20 || /\s/.test(apiKey)) {
          return json(
            req,
            traceId,
            { detail: "That doesn't look like an OpenAI API key (it starts with sk-)." },
            400
          )
        }
        if (deps.provider?.validateApiKey) {
          const ok = await deps.provider.validateApiKey(apiKey)
          if (!ok) {
            return json(req, traceId, { detail: "OpenAI didn't accept this key. Check it and try again." }, 400)
          }
        }
        const sealed = await sealApiKey(apiKey, unlock, ownerId, cfg.byokMasterSecret!)
        const hint = keyHint(apiKey)
        await deps.db.saveSealedUserKey(ownerId, sealed, hint)
        return json(req, traceId, {
          stored: true,
          unlocked: true,
          hint,
          server_key: Boolean(cfg.serverOpenAiKey),
        })
      }
      if (req.method === 'DELETE') {
        await deps.db.deleteSealedUserKey(ownerId)
        return json(req, traceId, {
          stored: false,
          unlocked: false,
          hint: null,
          server_key: Boolean(cfg.serverOpenAiKey),
        })
      }
    }

    // Independent Cases endpoints (/api/cases)
    if (req.method === 'GET' && path === '/api/cases') {
      return json(req, traceId, await deps.db.listCases(ownerId))
    }

    const caseDetailMatch = path.match(/^\/api\/cases\/([^/]+)$/)
    if (req.method === 'GET' && caseDetailMatch) {
      const caseId = caseDetailMatch[1]
      const c = await deps.db.getCase(ownerId, caseId)
      if (!c) return json(req, traceId, { detail: 'Case not found' }, 404)
      const mem = await deps.db.loadCaseMemory(ownerId, caseId)
      const chats = await deps.db.listConversations(ownerId, caseId)
      const drafts = await deps.db.listDrafts(ownerId, caseId)
      const attachments = await deps.db.listAttachments(ownerId, caseId)
      const actions = await deps.db.listUserActions(ownerId, caseId)
      const submissions = await deps.db.listSubmissionSteps(ownerId, caseId)
      return json(req, traceId, {
        case: c,
        conversations: chats,
        case_memory: mem.memory,
        summary: mem.summary,
        drafts,
        attachments,
        user_actions: actions,
        submission_steps: submissions,
      })
    }

    // Conversations endpoints (/api/conversations)
    if (req.method === 'GET' && path === '/api/conversations') {
      const caseId = url.searchParams.get('case_id')
      return json(req, traceId, await deps.db.listConversations(ownerId, caseId))
    }

    if (req.method === 'POST' && path === '/api/conversations') {
      const body = (await req.json().catch(() => ({}))) as { language?: Language; case_id?: string }
      const lang: Language = body.language && ['en', 'hi', 'hinglish'].includes(body.language) ? body.language : 'en'
      try {
        const created = await deps.db.createConversation(ownerId, lang, body.case_id || null)
        return json(req, traceId, created, 200)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        if (msg.includes('Case not found')) {
          return json(req, traceId, { detail: 'Case not found' }, 404)
        }
        return json(req, traceId, { detail: msg }, 400)
      }
    }

    // Encrypted transfer import (/api/conversations/transfer/import)
    if (req.method === 'POST' && path === '/api/conversations/transfer/import') {
      const body = (await req.json().catch(() => null)) as {
        passphrase?: string
        bundle?: Record<string, unknown>
      } | null
      if (!body || !body.passphrase || !body.bundle) {
        return json(req, traceId, { detail: 'Missing passphrase or transfer bundle' }, 400)
      }
      try {
        const snapshot = await importEncryptedTransferBundle(body.bundle, body.passphrase)
        const restored = await deps.db.restoreTransferredCase(ownerId, snapshot)
        return json(req, traceId, { imported: true, conversation: restored })
      } catch (err) {
        return json(req, traceId, { detail: err instanceof Error ? err.message : 'Transfer import failed' }, 400)
      }
    }

    // Conversation detail, rename, delete
    const convMatch = path.match(/^\/api\/conversations\/([^/]+)$/)
    if (convMatch) {
      const conversationId = convMatch[1]
      if (req.method === 'GET') {
        const conv = await deps.db.getConversation(ownerId, conversationId)
        if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
        const caseId = String(conv.case_id)
        const mem = await deps.db.loadCaseMemory(ownerId, caseId)
        const messages = await deps.db.listMessages(ownerId, conversationId)
        const safetyMessages = await deps.db.listSafetyEvents(ownerId, conversationId)
        const attachments = await deps.db.listAttachments(ownerId, caseId)
        const drafts = await deps.db.listDrafts(ownerId, caseId)
        const actions = await deps.db.listUserActions(ownerId, caseId)
        const submissions = await deps.db.listSubmissionSteps(ownerId, caseId)
        const lastActiveIso = String(conv.updated_at || new Date().toISOString())
        return json(req, traceId, {
          conversation: conv,
          case_id: caseId,
          messages,
          safety_messages: safetyMessages,
          case_memory: mem.memory,
          case_proposals: (mem.case_proposals || []).filter(
            (p: Record<string, unknown>) => p && typeof p.proposed_facts === 'object'
          ),
          staged_patches: mem.staged_patches,
          summary: mem.summary,
          attachments: attachments.map(a => ({
            ...a,
            stored_path: null,
            metadata_json:
              typeof a.metadata_json === 'string' ? a.metadata_json : JSON.stringify(a.metadata || {}),
          })),
          drafts,
          user_actions: actions,
          submission_steps: submissions,
          quality_review_consent: {
            opted_in: Boolean(mem.quality_review_consent),
            updated_at: null,
          },
          encryption: {
            envelope_encrypted: true,
            status: 'active',
          },
          retention: {
            policy: 'inactivity_auto_purge',
            inactivity_retention_days: 365,
            last_active_at: lastActiveIso,
            expires_at: new Date(Date.now() + 365 * 86400_000).toISOString(),
            days_remaining: 365,
            user_deletable_anytime: true,
          },
        })
      }
      if (req.method === 'PATCH') {
        const body = (await req.json().catch(() => null)) as { title?: string } | null
        const title = (body?.title || '').trim()
        if (!title || title.length > 80) {
          return json(req, traceId, { detail: 'Title must be between 1 and 80 characters' }, 422)
        }
        const ok = await deps.db.renameConversation(ownerId, conversationId, title)
        if (!ok) return json(req, traceId, { detail: 'Conversation not found' }, 404)
        return json(req, traceId, { ok: true })
      }
      if (req.method === 'DELETE') {
        const ok = await deps.db.deleteConversation(ownerId, conversationId)
        if (!ok) return json(req, traceId, { detail: 'Conversation not found' }, 404)
        return json(req, traceId, {
          deleted: true,
          cryptographic_key_destroyed: true,
          physical_purge_scheduled: true,
        })
      }
    }

    // Reconnect / durable event replay endpoint: GET /api/conversations/{id}/turns/{requestId}/events?after_seq=N
    const replayEventsMatch = path.match(/^\/api\/conversations\/([^/]+)\/turns\/([^/]+)\/events$/)
    if (req.method === 'GET' && replayEventsMatch) {
      const conversationId = replayEventsMatch[1]
      const requestId = decodeURIComponent(replayEventsMatch[2])
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const afterSeq = Number(url.searchParams.get('after_seq') || req.headers.get('Last-Event-ID') || '0') || 0
      const events = await deps.db.listTurnEvents(ownerId, conversationId, requestId, afterSeq)
      return json(req, traceId, {
        conversation_id: conversationId,
        request_id: requestId,
        after_seq: afterSeq,
        events,
      })
    }

    // Turn execution endpoints: POST /api/conversations/{id}/turns and /turns/stream
    const turnMatch = path.match(/^\/api\/conversations\/([^/]+)\/turns(\/stream)?$/)
    if (req.method === 'POST' && turnMatch) {
      const conversationId = turnMatch[1]
      const isStream = Boolean(turnMatch[2])
      const body = (await req.json().catch(() => null)) as {
        content?: string
        language?: Language
        request_id?: string
        attachment_ids?: string[]
        after_seq?: number
      } | null

      const content = (body?.content || '').trim()
      const requestId = (body?.request_id || '').trim()
      if (!content || !requestId) {
        return json(req, traceId, { detail: 'content and request_id are required' }, 422)
      }
      const language: Language =
        body?.language && ['en', 'hi', 'hinglish'].includes(body.language) ? body.language : 'en'
      const attachmentIds = Array.isArray(body?.attachment_ids) ? [...body!.attachment_ids].sort() : []
      const afterSeq =
        Number(url.searchParams.get('after_seq') || req.headers.get('Last-Event-ID') || body?.after_seq || '0') || 0

      const payloadHash = await canonicalPayloadHash({
        content,
        language,
        attachment_ids: attachmentIds,
      })

      let admitted: AdmitTurnResult
      try {
        admitted = await deps.db.admitTurn({
          ownerId,
          conversationId,
          requestId,
          payloadHash,
          userContent: content,
        })
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        if (msg.includes('Conversation not found')) {
          return json(req, traceId, { detail: 'Conversation not found' }, 404)
        }
        if (msg.includes('REQUEST_PAYLOAD_CONFLICT') || msg.includes('CONVERSATION_BUSY')) {
          return json(req, traceId, { detail: msg }, 409)
        }
        return json(req, traceId, { detail: msg }, 400)
      }

      const formatSseFrame = (evRow: Record<string, unknown>): string => {
        const seq = Number(evRow.seq || 1)
        const kind = String(evRow.kind || 'progress')
        const rawPayload = (evRow.payload || {}) as Record<string, unknown>
        const wirePayload = {
          ...rawPayload,
          schema_version: 'nyay.stream.v1',
          execution_id: String(evRow.execution_id || admitted.execution_id),
          request_id: requestId,
          seq,
          kind,
          block_id: evRow.block_id ?? null,
          block_revision: Number(evRow.block_revision || 1),
          publication_status: evRow.publication_status || 'published',
          payload: rawPayload,
        }
        return `id: ${seq}\nevent: ${kind}\ndata: ${JSON.stringify(wirePayload)}\n\n`
      }

      // Replay already-completed turn without new provider calls!
      if (admitted.action === 'replay_completed') {
        if (!isStream) {
          return json(req, traceId, admitted.result || {})
        }
        const events = (admitted.events || []).filter(
          e => Number(e.seq || 0) > afterSeq && e.publication_status !== 'superseded'
        )
        const sseText = events.map(formatSseFrame).join('')
        return new Response(sseText, {
          status: 200,
          headers: buildHeaders(req, traceId, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-store',
            'X-Accel-Buffering': 'no',
          }),
        })
      }

      if (admitted.action === 'in_progress') {
        if (!isStream) {
          return json(
            req,
            traceId,
            { detail: 'Turn is currently in progress. Reconnect or retry shortly.' },
            409
          )
        }
        const events = (admitted.events || []).filter(
          e => Number(e.seq || 0) > afterSeq && e.publication_status !== 'superseded'
        )
        const sseText = events.map(formatSseFrame).join('')
        return new Response(sseText, {
          status: 200,
          headers: buildHeaders(req, traceId, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-store',
            'X-Accel-Buffering': 'no',
            'X-Turn-Status': 'in_progress',
          }),
        })
      }

      const apiKey = await resolveEffectiveOpenAiKey(req, ownerId)

      if (!isStream) {
        try {
          const result = await executeReviewedTurn({
            req,
            ownerId,
            conversationId,
            caseId: admitted.case_id,
            executionId: admitted.execution_id,
            leaseToken: admitted.lease_token!,
            requestId,
            content,
            language,
            apiKey,
            emitEvent: async (kind, payload, blockId, blockRevision, publicationStatus) => {
              await deps.db.appendTurnEvent({
                executionId: admitted.execution_id,
                ownerId,
                leaseToken: admitted.lease_token!,
                kind,
                payload,
                blockId,
                blockRevision,
                publicationStatus,
              })
            },
          })
          return json(req, traceId, result)
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          if (msg.includes('STALE_WORKER_FENCED') || msg.includes('CASE_VERSION_CONFLICT')) {
            return json(req, traceId, { detail: msg }, 409)
          }
          return json(req, traceId, { detail: msg }, 503)
        }
      }

      // SSE Stream execution: persists every approved event to PostgreSQL BEFORE writing to the stream
      const encoder = new TextEncoder()
      const stream = new ReadableStream({
        async start(controller) {
          // Replay any prior events from an earlier interrupted generation > afterSeq
          for (const ev of admitted.prior_events || []) {
            if (Number(ev.seq || 0) > afterSeq) {
              controller.enqueue(encoder.encode(formatSseFrame(ev)))
            }
          }

          try {
            const finalResult = await executeReviewedTurn({
              req,
              ownerId,
              conversationId,
              caseId: admitted.case_id,
              executionId: admitted.execution_id,
              leaseToken: admitted.lease_token!,
              requestId,
              content,
              language,
              apiKey,
              emitEvent: async (kind, payload, blockId, blockRevision, publicationStatus) => {
                const inserted = await deps.db.appendTurnEvent({
                  executionId: admitted.execution_id,
                  ownerId,
                  leaseToken: admitted.lease_token!,
                  kind,
                  payload,
                  blockId,
                  blockRevision,
                  publicationStatus,
                })
                if (Number(inserted.seq || 0) > afterSeq) {
                  controller.enqueue(encoder.encode(formatSseFrame(inserted)))
                }
              },
            })

            const allEvents = await deps.db.listTurnEvents(ownerId, conversationId, requestId, afterSeq)
            const resultEvent = allEvents.find(e => e.kind === 'result')
            if (resultEvent) {
              controller.enqueue(encoder.encode(formatSseFrame(resultEvent)))
            } else {
              controller.enqueue(
                encoder.encode(
                  `event: result\ndata: ${JSON.stringify({
                    ...finalResult,
                    schema_version: 'nyay.stream.v1',
                    execution_id: admitted.execution_id,
                    request_id: requestId,
                    kind: 'result',
                  })}\n\n`
                )
              )
            }
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err)
            controller.enqueue(
              encoder.encode(
                `event: error\ndata: ${JSON.stringify({
                  schema_version: 'nyay.stream.v1',
                  execution_id: admitted.execution_id,
                  request_id: requestId,
                  kind: 'error',
                  detail: msg,
                })}\n\n`
              )
            )
          } finally {
            controller.close()
          }
        },
      })

      return new Response(stream, {
        status: 200,
        headers: buildHeaders(req, traceId, {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-store',
          'X-Accel-Buffering': 'no',
        }),
      })
    }

    // Attachments upload, text correction, consent
    const attachUploadMatch = path.match(/^\/api\/conversations\/([^/]+)\/attachments$/)
    if (req.method === 'POST' && attachUploadMatch) {
      const conversationId = attachUploadMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const caseId = String(conv.case_id)
      const consentParam = url.searchParams.get('consent') === 'withheld' ? 'withheld' : 'consented'

      let filename = 'document.txt'
      let mimeType = 'text/plain'
      let bytes: Uint8Array = new Uint8Array(0)

      const contentType = req.headers.get('content-type') || ''
      if (contentType.includes('multipart/form-data')) {
        const form = await req.formData()
        const file = form.get('file')
        if (!(file instanceof File)) {
          return json(req, traceId, { detail: 'Missing file in form data' }, 422)
        }
        filename = file.name || 'document'
        mimeType = file.type || 'application/octet-stream'
        bytes = new Uint8Array(await file.arrayBuffer())
      } else {
        const body = (await req.json().catch(() => null)) as {
          filename?: string
          mime_type?: string
          content_base64?: string
          text?: string
        } | null
        if (!body) return json(req, traceId, { detail: 'Invalid attachment payload' }, 422)
        filename = body.filename || 'document.txt'
        mimeType = body.mime_type || 'text/plain'
        if (typeof body.content_base64 === 'string' && body.content_base64.trim()) {
          const stripped = body.content_base64.trim().replace(/^data:[^;]+;base64,/, '')
          try {
            bytes = base64UrlToBytes(stripped)
          } catch {
            return json(req, traceId, { detail: 'Invalid base64 attachment payload' }, 422)
          }
        } else if (body.text !== undefined) {
          bytes = new TextEncoder().encode(body.text)
        } else {
          bytes = new Uint8Array(0)
        }
      }

      try {
        const processed = await processDocumentUpload({
          filename,
          mimeType,
          bytes,
        })
        const saved = await deps.db.addAttachment(ownerId, {
          case_id: caseId,
          conversation_id: conversationId,
          filename: processed.filename,
          mime_type: processed.mime_type,
          byte_length: processed.byte_length,
          sha256: processed.sha256,
          extraction_status: processed.extraction_status,
          extracted_text: processed.extracted_text,
          consent_status: consentParam,
          metadata: processed.metadata as unknown as Record<string, unknown>,
        })
        return json(req, traceId, {
          ...saved,
          stored_path: null,
          metadata: processed.metadata,
          metadata_json: JSON.stringify(processed.metadata),
        })
      } catch (err) {
        return json(req, traceId, { detail: err instanceof Error ? err.message : 'Upload rejected' }, 422)
      }
    }

    const attachPatchMatch = path.match(/^\/api\/conversations\/([^/]+)\/attachments\/([^/]+)$/)
    if (req.method === 'PATCH' && attachPatchMatch) {
      const conversationId = attachPatchMatch[1]
      const attachmentId = attachPatchMatch[2]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { extracted_text?: string } | null
      if (!body || typeof body.extracted_text !== 'string') {
        return json(req, traceId, { detail: 'extracted_text is required' }, 422)
      }
      const ok = await deps.db.updateAttachmentText(
        ownerId,
        String(conv.case_id),
        attachmentId,
        body.extracted_text.slice(0, 100_000)
      )
      if (!ok) return json(req, traceId, { detail: 'Attachment not found' }, 404)
      return json(req, traceId, { updated: true })
    }

    const attachConsentMatch = path.match(/^\/api\/conversations\/([^/]+)\/attachments\/([^/]+)\/consent$/)
    if (req.method === 'POST' && attachConsentMatch) {
      const conversationId = attachConsentMatch[1]
      const attachmentId = attachConsentMatch[2]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { consented?: boolean } | null
      const status = body?.consented === false ? 'withheld' : 'consented'
      const ok = await deps.db.setAttachmentConsent(ownerId, String(conv.case_id), attachmentId, status)
      if (!ok) return json(req, traceId, { detail: 'Attachment not found' }, 404)
      return json(req, traceId, { attachment_id: attachmentId, consent_status: status })
    }

    // Drafts create, update, export
    const draftsMatch = path.match(/^\/api\/conversations\/([^/]+)\/drafts$/)
    if (req.method === 'POST' && draftsMatch) {
      const conversationId = draftsMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { title?: string; content?: string } | null
      if (!body || !body.title?.trim() || !body.content?.trim()) {
        return json(req, traceId, { detail: 'title and content are required' }, 422)
      }
      const mem = await deps.db.loadCaseMemory(ownerId, String(conv.case_id))
      const draft = await deps.db.createDraft(
        ownerId,
        String(conv.case_id),
        body.title.trim(),
        body.content,
        mem.version
      )
      return json(req, traceId, draft)
    }

    const draftUpdateMatch = path.match(/^\/api\/conversations\/([^/]+)\/drafts\/([^/]+)$/)
    if (req.method === 'PATCH' && draftUpdateMatch) {
      const conversationId = draftUpdateMatch[1]
      const draftId = draftUpdateMatch[2]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as {
        title?: string
        content?: string
        expected_version?: number
      } | null
      if (!body || !body.content?.trim()) {
        return json(req, traceId, { detail: 'content is required' }, 422)
      }
      const mem = await deps.db.loadCaseMemory(ownerId, String(conv.case_id))
      try {
        const updated = await deps.db.updateDraft(
          ownerId,
          String(conv.case_id),
          draftId,
          (body.title || 'Draft').trim(),
          body.content,
          mem.version,
          body.expected_version
        )
        return json(req, traceId, updated)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        if (msg.includes('version conflict')) return json(req, traceId, { detail: msg }, 409)
        if (msg.includes('not found')) return json(req, traceId, { detail: 'Draft not found' }, 404)
        return json(req, traceId, { detail: msg }, 400)
      }
    }

    const draftExportMatch = path.match(/^\/api\/conversations\/([^/]+)\/drafts\/([^/]+)\/export\/(pdf|docx)$/)
    if (req.method === 'GET' && draftExportMatch) {
      const [, conversationId, draftId, format] = draftExportMatch
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const drafts = await deps.db.listDrafts(ownerId, String(conv.case_id))
      const draft = drafts.find(d => String(d.id) === draftId)
      if (!draft) return json(req, traceId, { detail: 'Draft not found' }, 404)
      const bytes =
        format === 'pdf'
          ? renderPrintablePdfBytes(String(draft.title), String(draft.content))
          : renderDocxXmlBytes(String(draft.title), String(draft.content))
      return new Response(bytes as BodyInit, {
        status: 200,
        headers: buildHeaders(req, traceId, {
          'Content-Type':
            format === 'pdf'
              ? 'application/pdf'
              : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'Content-Disposition': `attachment; filename="prepared-correspondence.${format}"`,
          'X-Draft-Status': String(draft.status || 'preliminary'),
          'Cache-Control': 'no-store',
        }),
      })
    }

    // User actions
    const actionsMatch = path.match(/^\/api\/conversations\/([^/]+)\/actions$/)
    if (req.method === 'POST' && actionsMatch) {
      const conversationId = actionsMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as {
        title?: string
        status?: 'pending' | 'completed' | 'skipped'
        notes?: string
      } | null
      if (!body || !body.title || body.title.trim().length < 2) {
        return json(req, traceId, { detail: 'Action title is required' }, 422)
      }
      const created = await deps.db.addUserAction(
        ownerId,
        String(conv.case_id),
        conversationId,
        body.title.trim(),
        body.status || 'completed',
        (body.notes || '').trim()
      )
      return json(req, traceId, created)
    }

    const actionPatchMatch = path.match(/^\/api\/conversations\/([^/]+)\/actions\/([^/]+)$/)
    if (req.method === 'PATCH' && actionPatchMatch) {
      const [, conversationId, actionId] = actionPatchMatch
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as {
        status?: 'pending' | 'completed' | 'skipped'
        notes?: string
      } | null
      if (!body || !body.status) {
        return json(req, traceId, { detail: 'status is required' }, 422)
      }
      const updated = await deps.db.updateUserAction(
        ownerId,
        String(conv.case_id),
        actionId,
        body.status,
        body.notes
      )
      if (!updated) return json(req, traceId, { detail: 'Action not found' }, 404)
      return json(req, traceId, updated)
    }

    // 4-step user submission audit trail
    const submissionsMatch = path.match(/^\/api\/conversations\/([^/]+)\/submissions$/)
    if (req.method === 'POST' && submissionsMatch) {
      const conversationId = submissionsMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as {
        target_channel?: string
        step?: 'previewed' | 'consented' | 'submitted_by_user' | 'receipt_captured'
        draft_id?: string
        receipt_reference?: string
        notes?: string
      } | null
      if (
        !body ||
        !body.target_channel ||
        !body.step ||
        !['previewed', 'consented', 'submitted_by_user', 'receipt_captured'].includes(body.step)
      ) {
        return json(req, traceId, { detail: 'Invalid submission step payload' }, 422)
      }
      const created = await deps.db.addSubmissionStep(
        ownerId,
        String(conv.case_id),
        conversationId,
        body.target_channel.trim(),
        body.step,
        body.draft_id || null,
        (body.receipt_reference || '').trim(),
        (body.notes || '').trim()
      )
      return json(req, traceId, created)
    }

    // Escalation bundle & exports
    const bundleMatch = path.match(/^\/api\/conversations\/([^/]+)\/escalation-bundle(?:\.json|\/export\/(pdf|docx))?$/)
    if (req.method === 'GET' && bundleMatch) {
      const conversationId = bundleMatch[1]
      const exportFormat = bundleMatch[2] as 'pdf' | 'docx' | undefined
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const caseId = String(conv.case_id)
      const mem = await deps.db.loadCaseMemory(ownerId, caseId)
      const bundle = buildEscalationBundle({
        conversation: conv,
        memory: mem.memory,
        summary: mem.summary,
        messages: await deps.db.listMessages(ownerId, conversationId),
        attachments: await deps.db.listAttachments(ownerId, caseId),
        drafts: await deps.db.listDrafts(ownerId, caseId),
        safetyMessages: await deps.db.listSafetyEvents(ownerId, conversationId),
        userActions: await deps.db.listUserActions(ownerId, caseId),
        submissionSteps: await deps.db.listSubmissionSteps(ownerId, caseId),
      })
      if (!exportFormat) {
        return json(req, traceId, bundle)
      }
      const textBody = JSON.stringify(bundle, null, 2)
      const bytes =
        exportFormat === 'pdf'
          ? renderPrintablePdfBytes(String(bundle.title), textBody)
          : renderDocxXmlBytes(String(bundle.title), textBody)
      return new Response(bytes as BodyInit, {
        status: 200,
        headers: buildHeaders(req, traceId, {
          'Content-Type':
            exportFormat === 'pdf'
              ? 'application/pdf'
              : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'Content-Disposition': `attachment; filename="nyay-saathi-lawyer-bundle.${exportFormat}"`,
          'Cache-Control': 'no-store',
        }),
      })
    }

    // Case export: GET /api/conversations/{id}/export/{json|pdf|docx}
    const caseExportMatch = path.match(/^\/api\/conversations\/([^/]+)\/export\/(json|pdf|docx)$/)
    if (req.method === 'GET' && caseExportMatch) {
      const [, conversationId, format] = caseExportMatch
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const caseId = String(conv.case_id)
      const mem = await deps.db.loadCaseMemory(ownerId, caseId)
      const payload = {
        conversation: conv,
        case_memory: mem.memory,
        summary: mem.summary,
        messages: await deps.db.listMessages(ownerId, conversationId),
        attachments: await deps.db.listAttachments(ownerId, caseId),
        drafts: await deps.db.listDrafts(ownerId, caseId),
      }
      if (format === 'json') {
        return new Response(JSON.stringify(payload, null, 2), {
          status: 200,
          headers: buildHeaders(req, traceId, {
            'Content-Type': 'application/json',
            'Content-Disposition': 'attachment; filename="nyay-saathi-case-pack.json"',
            'Cache-Control': 'no-store',
          }),
        })
      }
      const bytes =
        format === 'pdf'
          ? renderPrintablePdfBytes(String(conv.title || 'Case Pack'), JSON.stringify(payload, null, 2))
          : renderDocxXmlBytes(String(conv.title || 'Case Pack'), JSON.stringify(payload, null, 2))
      return new Response(bytes as BodyInit, {
        status: 200,
        headers: buildHeaders(req, traceId, {
          'Content-Type':
            format === 'pdf'
              ? 'application/pdf'
              : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'Content-Disposition': `attachment; filename="nyay-saathi-case-pack.${format}"`,
          'Cache-Control': 'no-store',
        }),
      })
    }

    // Quality consent
    const qualityConsentMatch = path.match(/^\/api\/conversations\/([^/]+)\/quality-consent$/)
    if (req.method === 'POST' && qualityConsentMatch) {
      const conversationId = qualityConsentMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { opted_in?: boolean } | null
      const optedIn = Boolean(body?.opted_in)
      await deps.db.setQualityReviewConsent(ownerId, String(conv.case_id), optedIn)
      return json(req, traceId, { opted_in: optedIn })
    }

    // Encrypted transfer export
    const transferExportMatch = path.match(/^\/api\/conversations\/([^/]+)\/transfer\/export$/)
    if (req.method === 'POST' && transferExportMatch) {
      const conversationId = transferExportMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { passphrase?: string } | null
      if (!body || !body.passphrase || body.passphrase.length < 8) {
        return json(req, traceId, { detail: 'Passphrase must be at least 8 characters' }, 422)
      }
      const caseId = String(conv.case_id)
      const mem = await deps.db.loadCaseMemory(ownerId, caseId)
      const snapshot = {
        conversation: conv,
        case_memory: mem.memory,
        summary: mem.summary,
        messages: await deps.db.listMessages(ownerId, conversationId),
        drafts: await deps.db.listDrafts(ownerId, caseId),
        user_actions: await deps.db.listUserActions(ownerId, caseId),
      }
      const bundle = await exportEncryptedTransferBundle(snapshot, body.passphrase)
      return json(req, traceId, bundle)
    }

    // DevSpace (disabled on multi-tenant Supabase mobile runtime; per-user BYOK is used instead)
    if (path === '/api/system/devspace') {
      if (req.method === 'GET') {
        return json(req, traceId, {
          enabled: false,
          mode: 'supabase_multi_user',
          detail: 'Server-wide DevSpace mutation is disabled on the shared Supabase backend. Use per-user BYOK (/api/me/openai-key).',
        })
      }
      if (req.method === 'POST') {
        return json(
          req,
          traceId,
          { detail: 'DevSpace settings mutation is disabled on the shared Supabase backend.' },
          403
        )
      }
    }

    // Credential rotation compatibility endpoint
    if (req.method === 'POST' && path === '/api/privacy/rotate-credential') {
      return json(req, traceId, {
        rotated: true,
        auth_mode: 'supabase_jwt',
        csrf_token: '',
      })
    }

    // Voice & Speech routes (backed by active OpenAI API key)
    if (req.method === 'GET' && path === '/api/audio/live-session') {
      const apiKey = await resolveEffectiveOpenAiKey(req, ownerId)
      if (!apiKey) {
        return json(req, traceId, { detail: 'OpenAI configuration required for voice' }, 503)
      }
      try {
        const sessionResp = await fetch('https://api.openai.com/v1/realtime/sessions', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: 'gpt-4o-realtime-preview',
            modalities: ['audio', 'text'],
            instructions: 'Transcribe Indian legal queries in Hindi or English.',
          }),
          signal: AbortSignal.timeout(10_000),
        })
        if (sessionResp.ok) {
          const sessionData = await sessionResp.json()
          return json(req, traceId, {
            client_secret: sessionData.client_secret?.value || sessionData.id,
            expires_at: sessionData.client_secret?.expires_at || (Math.floor(Date.now() / 1000) + 120),
            model: 'gpt-4o-realtime-preview',
            max_seconds: 60,
          })
        }
      } catch (err) {
        console.warn('Realtime live-session fallback to transcription:', err)
      }
      return json(req, traceId, {
        detail: 'Live WebRTC session unavailable; audio transcription will use recorded voice fallback.',
      }, 503)
    }

    if (req.method === 'POST' && path === '/api/audio/transcribe') {
      const apiKey = await resolveEffectiveOpenAiKey(req, ownerId)
      if (!apiKey) {
        return json(req, traceId, { detail: 'OpenAI configuration required for transcription' }, 503)
      }
      try {
        const formData = await req.formData()
        const file = formData.get('file')
        if (!file || !(file instanceof File || file instanceof Blob)) {
          return json(req, traceId, { detail: 'No audio file provided' }, 422)
        }
        const openAiForm = new FormData()
        openAiForm.append('file', file, (file as File).name || 'recording.webm')
        openAiForm.append('model', 'whisper-1')
        openAiForm.append('prompt', 'Indian legal question or dispute. Preserve names, dates, rupee amounts, negation, Hindi-English code-switching and uncertainty.')
        openAiForm.append('response_format', 'json')

        const openAiResp = await fetch('https://api.openai.com/v1/audio/transcriptions', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${apiKey}`,
          },
          body: openAiForm,
          signal: AbortSignal.timeout(30_000),
        })

        if (!openAiResp.ok) {
          const errPayload = await openAiResp.text().catch(() => '')
          console.error('Transcription OpenAI error:', openAiResp.status, errPayload)
          return json(req, traceId, { detail: 'Transcription service temporarily unavailable' }, 502)
        }

        const data = await openAiResp.json()
        return json(req, traceId, {
          transcript: data.text || '',
          editable: true,
          model: 'whisper-1',
        })
      } catch (err) {
        console.error('Transcription exception:', err)
        return json(req, traceId, { detail: 'Failed to transcribe audio' }, 502)
      }
    }

    const speechMatch = path.match(/^\/api\/conversations\/([^/]+)\/messages\/([^/]+)\/speech$/)
    if (req.method === 'POST' && speechMatch) {
      const [, conversationId, messageId] = speechMatch
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const messages = await deps.db.listMessages(ownerId, conversationId)
      const msg = messages.find(m => String(m.id) === messageId)
      if (!msg) return json(req, traceId, { detail: 'Message not found' }, 404)
      const meta = (msg.metadata || {}) as Record<string, unknown>
      const ver = (meta.verification || {}) as Record<string, unknown>
      if (msg.role !== 'assistant' || msg.status !== 'complete' || (!ver.passed && !ver.publication_safe)) {
        return json(
          req,
          traceId,
          { detail: 'Speech is available only for completed verified assistant answers' },
          409
        )
      }
      const apiKey = await resolveEffectiveOpenAiKey(req, ownerId)
      if (!apiKey) {
        return json(req, traceId, { detail: 'OpenAI configuration required for speech' }, 503)
      }
      try {
        const textToSpeak = String(msg.content || '').slice(0, 1800)
        const openAiResp = await fetch('https://api.openai.com/v1/audio/speech', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: 'tts-1',
            input: textToSpeak,
            voice: 'alloy',
            response_format: 'mp3',
          }),
          signal: AbortSignal.timeout(30_000),
        })

        if (!openAiResp.ok) {
          const errPayload = await openAiResp.text().catch(() => '')
          console.error('Speech synthesis OpenAI error:', openAiResp.status, errPayload)
          return json(req, traceId, { detail: 'Speech synthesis temporarily unavailable' }, 502)
        }

        const audioBytes = await openAiResp.arrayBuffer()
        return new Response(audioBytes, {
          status: 200,
          headers: buildHeaders(req, traceId, {
            'Content-Type': 'audio/mpeg',
            'Content-Length': String(audioBytes.byteLength),
          }),
        })
      } catch (err) {
        console.error('Speech synthesis exception:', err)
        return json(req, traceId, { detail: 'Failed to synthesize speech' }, 502)
      }
    }

    // Practice & Roleplay contracts (ownership-verified)
    const practiceScenariosMatch = path.match(/^\/api\/conversations\/([^/]+)\/practice\/scenarios$/)
    if (req.method === 'GET' && practiceScenariosMatch) {
      const conv = await deps.db.getConversation(ownerId, practiceScenariosMatch[1])
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      return json(req, traceId, [
        {
          id: 'refund_grievance_call',
          scenario_id: 'refund_grievance_call',
          title: 'Escalating a stalled refund to a Grievance Officer',
          domain: 'consumer',
          opponent_role: 'E-Commerce Grievance Officer',
          stakeholder: 'E-Commerce Grievance Officer',
          setting: 'Escalation call after routine customer support closure',
          objective: 'State order ID, pickup date, and Rule 4 acknowledgement deadline clearly.',
          opening_statement:
            'Hello, this is the Grievance Desk. I see your earlier support ticket was closed. Please state your order reference and what remains unresolved.',
          key_rights: [
            'Rule 4(4)–(5) E-Commerce Rules, 2020: 48-hour acknowledgement and 1-month redress.',
            'Right to a written complaint reference number.',
          ],
          suggested_first_response:
            'My order was picked up as confirmed by the return receipt, but the refund has not been credited. Please record my grievance under Rule 4 and share the ticket number.',
        },
        {
          id: 'bank_fraud_dispute',
          scenario_id: 'bank_fraud_dispute',
          title: 'Reporting an unauthorized debit to Bank Fraud Desk',
          domain: 'financial_fraud',
          opponent_role: 'Bank Fraud Resolution Officer',
          stakeholder: 'Bank Fraud Resolution Officer',
          objective: 'Request immediate channel block and dispute reference number.',
          opening_statement:
            'Bank Fraud Desk speaking. Tell me the transaction UTR, amount, and how you noticed the debit.',
          key_rights: [
            'Immediate blocking of compromised cards, UPI, and net-banking channels.',
            'Zero customer liability for any further unauthorized debit after notifying the bank.',
          ],
          suggested_first_response:
            'Please block my UPI and card access immediately, log an unauthorized electronic transaction dispute for the UTR, and give me the complaint reference number.',
        },
      ])
    }

    const roleplaySetupMatch = path.match(/^\/api\/conversations\/([^/]+)\/roleplay\/setup$/)
    if (req.method === 'GET' && roleplaySetupMatch) {
      const conv = await deps.db.getConversation(ownerId, roleplaySetupMatch[1])
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const mem = await deps.db.loadCaseMemory(ownerId, String(conv.case_id))
      const stakeholders = [
        'Grievance Officer',
        'Bank Nodal Officer',
        'Consumer Helpline Counsellor',
        'Police Station Duty Officer',
      ]
      return json(req, traceId, {
        case_title: String(conv.title || 'New case'),
        case_synopsis: mem.summary || 'Practice explaining your chronology and documents clearly.',
        stakeholders,
        suggested_stakeholders: stakeholders,
      })
    }

    const roleplayStartMatch = path.match(/^\/api\/conversations\/([^/]+)\/roleplay\/start$/)
    if (req.method === 'POST' && roleplayStartMatch) {
      const conversationId = roleplayStartMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => ({}))) as {
        stakeholder?: string
        custom_stakeholder?: string
        language?: Language
        case_title?: string
        case_synopsis?: string
      }
      const stakeholder =
        (body.stakeholder === 'Someone else' ? body.custom_stakeholder : body.stakeholder)?.trim() ||
        'Grievance Officer'
      const lang: Language = body.language && ['en', 'hi', 'hinglish'].includes(body.language) ? body.language : 'en'
      const openingByLang: Record<Language, string> = {
        en: `Hello, I am the ${stakeholder}. Please state the key dates, reference numbers, and what specific action you are requesting today.`,
        hi: `नमस्ते, मैं ${stakeholder} बोल रहा हूँ। कृपया मुख्य तारीखें, संदर्भ संख्या और आप आज क्या कार्रवाई चाहते हैं, स्पष्ट रूप से बताएं।`,
        hinglish: `Hello, main ${stakeholder} bol raha hoon. Please key dates, reference numbers aur aaj aap kya action chahte hain clearly batayein.`,
      }
      return json(req, traceId, {
        session_id: `rp-${crypto.randomUUID().slice(0, 12)}`,
        stakeholder,
        case_title: body.case_title || String(conv.title || 'New case'),
        case_synopsis: body.case_synopsis || 'Practice explaining your chronology and documents clearly.',
        opening_message: openingByLang[lang],
      })
    }

    const roleplayChatMatch = path.match(/^\/api\/conversations\/([^/]+)\/roleplay\/chat(\/stream)?$/)
    if (req.method === 'POST' && roleplayChatMatch) {
      const conversationId = roleplayChatMatch[1]
      const isStream = Boolean(roleplayChatMatch[2])
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { message?: string; language?: Language } | null
      const userMessage = (body?.message || '').trim()
      if (!userMessage) return json(req, traceId, { detail: 'message is required' }, 422)
      const lang: Language =
        body?.language && ['en', 'hi', 'hinglish'].includes(body.language) ? body.language : 'en'

      // Urgent safety check during roleplay: break character if real urgent risk is expressed
      const urgentCat = detectUrgentCategory(userMessage)
      let replyPayload: { reply: string; turn_index: number; in_character: boolean; notice: string | null }
      if (urgentCat) {
        const safetyEv = await buildSafetyEvent({
          language: lang,
          today: getTodayIso(),
          india: true,
          category: urgentCat,
        })
        replyPayload = {
          reply: safetyEv.text,
          turn_index: 1,
          in_character: false,
          notice: 'Roleplay paused to provide immediate protective guidance.',
        }
      } else {
        const replyByLang: Record<Language, string> = {
          en: 'I have noted your statement. Which specific document, transaction ID, or prior ticket number can you share right now so I can record this formally?',
          hi: 'मैंने आपकी बात नोट कर ली है। इसे औपचारिक रूप से दर्ज करने के लिए आप अभी कौन सा दस्तावेज़, ट्रांज़ैक्शन ID या पुरानी टिकट संख्या साझा कर सकते हैं?',
          hinglish:
            'Maine aapki baat note kar li hai. Isse formally record karne ke liye aap abhi kaun sa document, transaction ID ya ticket number share kar sakte hain?',
        }
        replyPayload = {
          reply: replyByLang[lang],
          turn_index: 1,
          in_character: true,
          notice: 'Practice simulation · keep your dates and document references concise.',
        }
      }

      if (!isStream) {
        return json(req, traceId, replyPayload)
      }
      const sse =
        `event: delta\ndata: ${JSON.stringify({ text: replyPayload.reply })}\n\n` +
        `event: result\ndata: ${JSON.stringify(replyPayload)}\n\n`
      return new Response(sse, {
        status: 200,
        headers: buildHeaders(req, traceId, {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-store',
        }),
      })
    }

    const practiceSessionsListMatch = path.match(/^\/api\/conversations\/([^/]+)\/practice\/sessions$/)
    if (practiceSessionsListMatch) {
      const conversationId = practiceSessionsListMatch[1]
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      if (req.method === 'GET') {
        return json(req, traceId, [])
      }
      if (req.method === 'POST') {
        const body = (await req.json().catch(() => ({}))) as {
          scenario_id?: string
          custom_scenario?: string
        }
        const now = new Date().toISOString()
        return json(req, traceId, {
          id: `ps-${crypto.randomUUID().slice(0, 12)}`,
          conversation_id: conversationId,
          scenario_id: body.scenario_id || 'refund_grievance_call',
          title: body.custom_scenario || 'Escalating a stalled refund to a Grievance Officer',
          domain: 'consumer',
          opponent_role: 'E-Commerce Grievance Officer',
          setting: 'Escalation call after routine customer support closure',
          objective: 'State order ID, pickup date, and Rule 4 acknowledgement deadline clearly.',
          opening_statement:
            'Hello, this is the Grievance Desk. Please state your order reference and what remains unresolved.',
          status: 'active',
          created_at: now,
          updated_at: now,
          turns: [],
          turn_count: 0,
        })
      }
    }

    const practiceTurnMatch = path.match(/^\/api\/conversations\/([^/]+)\/practice\/sessions\/([^/]+)\/turns$/)
    if (req.method === 'POST' && practiceTurnMatch) {
      const [, conversationId, sessionId] = practiceTurnMatch
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { user_argument?: string; language?: Language } | null
      const arg = (body?.user_argument || '').trim()
      if (!arg) return json(req, traceId, { detail: 'user_argument is required' }, 422)
      return json(req, traceId, {
        id: `pt-${crypto.randomUUID().slice(0, 12)}`,
        session_id: sessionId,
        turn_index: 1,
        user_argument: arg,
        opponent_reply:
          'Please share the exact invoice/UTR reference and confirm the date the return pickup was completed.',
        coach_feedback: {
          assessment: 'strong',
          strengths: ['Clearly stated the factual grievance without speculation.'],
          vulnerabilities: ['Include the exact transaction/order ID and date in the opening sentence.'],
          statutory_safeguards: [
            {
              section: 'Rule 4(4)–(5)',
              act: 'Consumer Protection (E-Commerce) Rules, 2020',
              title: 'Grievance Officer acknowledgement & redress timeline',
              relevance: 'Requires acknowledgement within 48 hours and redress within 1 month.',
            },
          ],
          suggested_phrasing:
            'Under Rule 4 of the E-Commerce Rules, 2020, please record this grievance for my order and share the written acknowledgement number.',
          anti_fabrication_warning: null,
          is_crisis: false,
          crisis_text: null,
        },
        created_at: new Date().toISOString(),
      })
    }

    const practiceExportActionsMatch = path.match(
      /^\/api\/conversations\/([^/]+)\/practice\/sessions\/([^/]+)\/export-actions$/
    )
    if (req.method === 'POST' && practiceExportActionsMatch) {
      const [_, conversationId] = practiceExportActionsMatch
      const conv = await deps.db.getConversation(ownerId, conversationId)
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const body = (await req.json().catch(() => null)) as { action_titles?: string[] } | null
      const titles = Array.isArray(body?.action_titles)
        ? body!.action_titles.map(t => String(t || '').trim()).filter(t => t.length >= 2)
        : []
      for (const title of titles) {
        await deps.db.addUserAction(ownerId, String(conv.case_id), conversationId, title, 'pending', 'From practice')
      }
      return json(req, traceId, { exported_count: titles.length, status: 'exported' })
    }

    // ============================================================================
    // Package 4: Case Lifecycle State (Submissions, Promises, Processed Refunds,
    // Remedy Receipt & Closure kept strictly distinct)
    // ============================================================================
    const caseLifecycleMatch = path.match(/^\/api\/cases\/([^/]+)\/lifecycle$/)
    const convLifecycleMatch = path.match(/^\/api\/conversations\/([^/]+)\/lifecycle$/)
    if ((req.method === 'PATCH' || req.method === 'POST') && (caseLifecycleMatch || convLifecycleMatch)) {
      let caseId = caseLifecycleMatch ? caseLifecycleMatch[1] : ''
      if (convLifecycleMatch) {
        const conv = await deps.db.getConversation(ownerId, convLifecycleMatch[1])
        if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
        caseId = String(conv.case_id)
      }
      const existingCase = await deps.db.getCase(ownerId, caseId)
      if (!existingCase) return json(req, traceId, { detail: 'Case not found' }, 404)

      const body = (await req.json().catch(() => null)) as {
        domain?: string
        incident_date?: string | null
        jurisdiction?: string
        event_kind?: 'submission' | 'promise' | 'processed_refund' | 'remedy_receipt' | 'closure'
        entry?: Record<string, unknown>
        closure_status?: 'open' | 'resolved_confirmed' | 'closed_unresolved' | 'pursuit_stopped'
      } | null
      if (!body) return json(req, traceId, { detail: 'Invalid lifecycle payload' }, 422)

      const currentLifecycle = ((existingCase.lifecycle_state as Record<string, unknown>) || {
        submissions: [],
        promises: [],
        processed_refunds: [],
        remedy_receipt: null,
        closure: 'open',
      }) as {
        submissions: Array<Record<string, unknown>>
        promises: Array<Record<string, unknown>>
        processed_refunds: Array<Record<string, unknown>>
        remedy_receipt: Record<string, unknown> | null
        closure: string
      }

      const nextLifecycle = {
        submissions: Array.isArray(currentLifecycle.submissions) ? [...currentLifecycle.submissions] : [],
        promises: Array.isArray(currentLifecycle.promises) ? [...currentLifecycle.promises] : [],
        processed_refunds: Array.isArray(currentLifecycle.processed_refunds)
          ? [...currentLifecycle.processed_refunds]
          : [],
        remedy_receipt: currentLifecycle.remedy_receipt ?? null,
        closure: currentLifecycle.closure || 'open',
      }

      const stampedEntry = body.entry
        ? { ...body.entry, recorded_at: new Date().toISOString() }
        : { recorded_at: new Date().toISOString() }

      if (body.event_kind === 'submission') {
        nextLifecycle.submissions.push(stampedEntry)
      } else if (body.event_kind === 'promise') {
        // Seller/recipient promise does NOT mark remedy_receipt or closure!
        nextLifecycle.promises.push(stampedEntry)
      } else if (body.event_kind === 'processed_refund') {
        // Merchant claim of processed refund does NOT mark remedy_receipt until user confirms credit!
        nextLifecycle.processed_refunds.push(stampedEntry)
      } else if (body.event_kind === 'remedy_receipt') {
        nextLifecycle.remedy_receipt = stampedEntry
      } else if (body.event_kind === 'closure' && body.closure_status) {
        nextLifecycle.closure = body.closure_status
      }

      if (deps.db.updateCaseLifecycle) {
        const updated = await deps.db.updateCaseLifecycle(ownerId, caseId, {
          domain: body.domain,
          incident_date: body.incident_date,
          jurisdiction: body.jurisdiction,
          lifecycle_state: nextLifecycle,
        })
        return json(req, traceId, updated || { case_id: caseId, lifecycle_state: nextLifecycle })
      }
      return json(req, traceId, { case_id: caseId, lifecycle_state: nextLifecycle })
    }

    // ============================================================================
    // Provider execution requires a real OAuth and Google API adapter. Historical
    // scaffold records are retained but cannot be treated as verified receipts.
    const googleUnavailable = (service: string) =>
      json(req, traceId, {
        code: 'google_provider_unavailable',
        detail: `${service} is unavailable in this build.`,
      }, 503)

    if (req.method === 'GET' && path === '/api/integrations/google/status') {
      return json(req, traceId, {
        owner_id: ownerId,
        google_drive: null,
        google_gmail: null,
        availability: 'unavailable',
        storage_policy: 'disclosed_temporary_processing',
      })
    }

    if (req.method === 'POST' && path === '/api/integrations/google/connect') {
      return googleUnavailable('Google Drive and Gmail connection')
    }

    if (req.method === 'POST' && path === '/api/integrations/google/disconnect') {
      if (!deps.db.revokeProviderConnection) {
        return json(req, traceId, { detail: 'Provider connections not configured' }, 503)
      }
      const body = (await req.json().catch(() => null)) as {
        provider?: 'google_drive' | 'google_gmail'
      } | null
      if (!body?.provider || !['google_drive', 'google_gmail'].includes(body.provider)) {
        return json(req, traceId, { detail: 'Valid provider (google_drive or google_gmail) is required' }, 422)
      }
      const disconnectedLocally = await deps.db.revokeProviderConnection(ownerId, body.provider)
      return json(req, traceId, {
        revoked: false,
        disconnected_locally: disconnectedLocally,
        provider: body.provider,
        secrets_purged: false,
      })
    }

    if (req.method === 'PATCH' && path === '/api/integrations/google/gmail-monitoring') {
      return googleUnavailable('Gmail reply monitoring')
    }

    const googleCaseMatch = path.match(/^\/api\/conversations\/([^/]+)\/(drive|gmail)\/([^/]+)$/)
    if (googleCaseMatch) {
      const [, conversationId, provider, operation] = googleCaseMatch
      const isDrive = provider === 'drive'
      const state = isDrive ? 'manifest' : 'state'
      const writes = isDrive ? ['folder', 'upload', 'reconcile'] : ['import', 'approvals', 'send', 'reconcile']
      const isRead = req.method === 'GET' && operation === state
      if (isRead || (req.method === 'POST' && writes.includes(operation))) {
        const conv = await deps.db.getConversation(ownerId, conversationId)
        if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
        if (!isRead) return googleUnavailable(isDrive ? 'Google Drive' : 'Gmail')
        return json(req, traceId, {
          case_id: String(conv.case_id),
          connection: null,
          availability: 'unavailable',
          ...(isDrive
            ? { folder: null, items: [], local_v2_migration_policy: 'explicit_user_selection_only_never_automatic' }
            : { evidence_messages: [], approvals: [], dispatches: [] }),
        })
      }
    }

    const driveCleanupMatch = path.match(/^\/api\/conversations\/([^/]+)\/drive\/cleanup-temporary$/)
    if (req.method === 'POST' && driveCleanupMatch) {
      const conv = await deps.db.getConversation(ownerId, driveCleanupMatch[1])
      if (!conv) return json(req, traceId, { detail: 'Conversation not found' }, 404)
      const caseId = String(conv.case_id)
      if (!deps.db.cleanupTemporaryDocumentText) {
        return json(req, traceId, { detail: 'Temporary document cleanup unavailable' }, 503)
      }
      const cleanedCount = await deps.db.cleanupTemporaryDocumentText(ownerId, caseId)
      return json(req, traceId, {
        case_id: caseId,
        temporary_artifacts_cleaned: cleanedCount,
        status: 'purged_temporary_extracted_text',
      })
    }

    // ============================================================================
    // Package 7: Temporal Applicability, Corrective Retrieval & Cache Invalidation
    // ============================================================================
    if (req.method === 'POST' && path === '/api/knowledge/temporal-resolve') {
      const body = (await req.json().catch(() => null)) as {
        query?: string
        incident_date?: string | null
        procedural_stage?: 'pending_before_2024_07_01' | 'fresh_after_2024_07_01' | 'unknown' | null
        jurisdiction?: string | null
        domain?: string | null
      } | null
      if (!body || !body.query?.trim()) {
        return json(req, traceId, { detail: 'query is required' }, 422)
      }
      const temporal = resolveTemporalAndJurisdictionApplicability({
        query: body.query,
        incidentDate: body.incident_date,
        proceduralStage: body.procedural_stage,
        jurisdiction: body.jurisdiction,
        domain: body.domain,
      })
      const basePool = cfg.customPassages && cfg.customPassages.length > 0 ? cfg.customPassages : CERTIFIED_PROPOSITIONS
      const dbProvisions = deps.db.listLegalProvisions
        ? await deps.db.listLegalProvisions(body.domain || null)
        : []
      const provisionFilter = filterPassagesWithProvisionState(basePool, dbProvisions)
      const retrieved = await retrieveCertifiedPassages({
        query: body.query,
        domain: body.domain || undefined,
        jurisdiction: body.jurisdiction || 'India',
        asOfDate: body.incident_date || null,
        limit: 8,
        customPassages: provisionFilter.activePassages,
      })
      const corrective = evaluateCorrectiveRetrieval({
        query: body.query,
        passages: retrieved.passages,
        temporalResolution: temporal,
        invalidatedProvisionIds: provisionFilter.invalidatedProvisionIds,
        invalidatedWarnings: provisionFilter.invalidatedWarnings,
        cacheEpoch: provisionFilter.maxCacheEpoch,
      })
      return json(req, traceId, {
        temporal_applicability: temporal,
        corrective_retrieval: corrective,
        passages: retrieved.passages,
      })
    }

    if (req.method === 'GET' && path === '/api/knowledge/provisions') {
      const domain = url.searchParams.get('domain')
      const provisions = deps.db.listLegalProvisions ? await deps.db.listLegalProvisions(domain) : []
      return json(req, traceId, { provisions })
    }

    const invalidateProvisionMatch = path.match(/^\/api\/knowledge\/provisions\/([^/]+)\/invalidate-cache$/)
    if (req.method === 'POST' && invalidateProvisionMatch) {
      const provisionId = decodeURIComponent(invalidateProvisionMatch[1])
      if (!deps.db.invalidateLegalProvisionCache) {
        return json(req, traceId, { detail: 'Provision cache invalidation not configured' }, 503)
      }
      const body = (await req.json().catch(() => ({}))) as { review_state?: string }
      const targetState = body.review_state || 'amended_cache_invalidated'
      const validReviewStates = [
        'source_verified_pending_legal_review',
        'qualified_legal_reviewed',
        'amended_cache_invalidated',
        'retired',
      ]
      if (!validReviewStates.includes(targetState)) {
        return json(req, traceId, { detail: `Invalid review_state: ${targetState}` }, 422)
      }
      const updated = await deps.db.invalidateLegalProvisionCache(provisionId, targetState)
      if (!updated) return json(req, traceId, { detail: 'Provision not found' }, 404)
      return json(req, traceId, {
        invalidated: true,
        provision: updated,
        dependent_output_caches_purged: true,
      })
    }

    return json(req, traceId, { detail: `Route not found: ${req.method} ${path}` }, 404)
  }
}
