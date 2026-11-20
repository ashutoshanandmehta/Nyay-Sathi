// Supabase Edge Function entrypoint for nyay-api (Deno 2 runtime).
// Deployed to project daojcrxjjkqoirqbvhjn (ap-northeast-1).
// Never modifies or connects to the Vercel demo or unrelated projects.

import { createClient } from 'jsr:@supabase/supabase-js@2.119.1'
import type { CaseMemoryModel, Language } from './contracts.ts'
import { normalizeCaseMemory } from './contracts.ts'
import type { AdmitTurnResult, AuthenticatedUser, DatabasePort } from './handler.ts'
import { createNyayApiHandler } from './handler.ts'
import { OpenAiResponsesProvider } from './openai-provider.ts'
import { OpenAiBackgroundProvider } from './background-provider.ts'
import { createResumableHandler } from './resumable-http.ts'
import { prepareSafety } from './resumable-turn.ts'
import { DEFAULT_RUNTIME, runtimeConfig } from './runtime-config.ts'
import { createOpenAiQueryEmbedder, createRequiredSemanticRetriever, createVersionedQueryEmbedder } from './semantic-retrieval.ts'
import { LEGAL_CORPUS_COVERAGE_DECLARATION, type SupabaseHybridRpcRow } from './legal-retrieval.ts'
import type { VerifiedContactRecord } from './safety.ts'

declare const Deno: {
  env: { get(key: string): string | undefined }
  serve(handler: (req: Request) => Promise<Response> | Response): void
}

function createSupabaseDatabaseAdapter(supabaseUrl: string, serviceRoleKey: string, anonKey: string): DatabasePort {
  const admin = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: {fetch: (input, init) => fetch(input, {...init, signal: AbortSignal.timeout(9_000)})},
  })

  const userClient = (jwt: string) =>
    createClient(supabaseUrl, anonKey, {
      global: { headers: { Authorization: `Bearer ${jwt}` } },
      auth: { persistSession: false, autoRefreshToken: false },
    })

  return {
    async authenticate(token: string | null): Promise<AuthenticatedUser | null> {
      if (!token) return null
      const { data, error } = await admin.auth.getUser(token)
      if (error || !data?.user) return null
      return {
        id: data.user.id,
        is_anonymous: Boolean(data.user.is_anonymous),
        email: data.user.email,
      }
    },

    async createConversation(ownerId: string, language: Language, caseId?: string | null) {
      let cid = caseId
      if (!cid) {
        const { data: createdCase, error: caseErr } = await admin
          .from('nyay_cases')
          .insert({ owner_id: ownerId })
          .select('*')
          .single()
        if (caseErr || !createdCase) throw new Error(caseErr?.message || 'Failed to create case')
        cid = createdCase.id
      } else {
        const { data: foundCase } = await admin
          .from('nyay_cases')
          .select('id')
          .eq('id', cid)
          .eq('owner_id', ownerId)
          .maybeSingle()
        if (!foundCase) throw new Error('Case not found')
      }
      const { data: conv, error } = await admin
        .from('nyay_conversations')
        .insert({ case_id: cid, owner_id: ownerId, language })
        .select('*')
        .single()
      if (error || !conv) throw new Error(error?.message || 'Failed to create conversation')
      return conv
    },

    async listCases(ownerId: string) {
      const { data } = await admin
        .from('nyay_cases')
        .select('*')
        .eq('owner_id', ownerId)
        .order('updated_at', { ascending: false })
      return data || []
    },

    async getCase(ownerId: string, caseId: string) {
      const { data } = await admin
        .from('nyay_cases')
        .select('*')
        .eq('id', caseId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      return data || null
    },

    async listConversations(ownerId: string, caseId?: string | null) {
      let q = admin.from('nyay_conversations').select('*').eq('owner_id', ownerId)
      if (caseId) q = q.eq('case_id', caseId)
      const { data } = await q.order('updated_at', { ascending: false })
      return data || []
    },

    async getConversation(ownerId: string, conversationId: string) {
      const { data } = await admin
        .from('nyay_conversations')
        .select('*')
        .eq('id', conversationId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      return data || null
    },

    async renameConversation(ownerId: string, conversationId: string, title: string) {
      const { data } = await admin
        .from('nyay_conversations')
        .update({ title, updated_at: new Date().toISOString() })
        .eq('id', conversationId)
        .eq('owner_id', ownerId)
        .select('id')
      return Boolean(data && data.length > 0)
    },

    async deleteConversation(ownerId: string, conversationId: string) {
      const { data } = await admin
        .from('nyay_conversations')
        .delete()
        .eq('id', conversationId)
        .eq('owner_id', ownerId)
        .select('id')
      return Boolean(data && data.length > 0)
    },

    async loadCaseMemory(ownerId: string, caseId: string) {
      const { data } = await admin
        .from('nyay_case_memory')
        .select('*')
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      const version = Number(data?.version || 0)
      return {
        version,
        memory: normalizeCaseMemory(data?.memory, version),
        summary: String(data?.summary || ''),
        staged_patches: Array.isArray(data?.staged_patches) ? data.staged_patches : [],
        case_proposals: Array.isArray(data?.case_proposals) ? data.case_proposals : [],
        quality_review_consent: Boolean(data?.quality_review_consent),
      }
    },

    async setQualityReviewConsent(ownerId: string, caseId: string, optedIn: boolean) {
      const { data: existing } = await admin
        .from('nyay_case_memory')
        .select('case_id')
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      if (existing) {
        await admin
          .from('nyay_case_memory')
          .update({ quality_review_consent: optedIn, updated_at: new Date().toISOString() })
          .eq('case_id', caseId)
          .eq('owner_id', ownerId)
      } else {
        await admin
          .from('nyay_case_memory')
          .insert({ case_id: caseId, owner_id: ownerId, quality_review_consent: optedIn })
      }
      return true
    },

    async listMessages(ownerId: string, conversationId: string) {
      const { data } = await admin
        .from('nyay_messages')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('conversation_id', conversationId)
        .order('created_at', { ascending: true })
      return data || []
    },

    async listSafetyEvents(ownerId: string, conversationId: string) {
      const { data: execs } = await admin
        .from('nyay_turn_executions')
        .select('id')
        .eq('owner_id', ownerId)
        .eq('conversation_id', conversationId)
      const execIds = (execs || []).map(e => e.id)
      if (!execIds.length) return []
      const { data: events } = await admin
        .from('nyay_turn_events')
        .select('payload')
        .eq('owner_id', ownerId)
        .eq('kind', 'safety')
        .in('execution_id', execIds)
        .order('id', { ascending: true })
      return (events || []).map(e => e.payload as Record<string, unknown>)
    },

    async listTurnEvents(ownerId: string, conversationId: string, requestId: string, afterSeq = 0) {
      const { data: exec } = await admin
        .from('nyay_turn_executions')
        .select('id')
        .eq('owner_id', ownerId)
        .eq('conversation_id', conversationId)
        .eq('request_id', requestId)
        .maybeSingle()
      if (!exec) return []
      const { data } = await admin
        .from('nyay_turn_events')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('execution_id', exec.id)
        .gt('seq', afterSeq)
        .order('seq', { ascending: true })
      return data || []
    },

    async listAttachments(ownerId: string, caseId: string) {
      const { data } = await admin
        .from('nyay_case_documents')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: true })
      return data || []
    },

    async addAttachment(ownerId, record) {
      const { data, error } = await admin
        .from('nyay_case_documents')
        .insert({ ...record, owner_id: ownerId })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to save attachment')
      return data
    },

    async updateAttachmentText(ownerId, caseId, attachmentId, extractedText) {
      const { data } = await admin
        .from('nyay_case_documents')
        .update({
          extracted_text: extractedText,
          extraction_status: 'user_corrected',
          updated_at: new Date().toISOString(),
        })
        .eq('id', attachmentId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .select('id')
      return Boolean(data && data.length > 0)
    },

    async setAttachmentConsent(ownerId, caseId, attachmentId, consentStatus) {
      const { data } = await admin
        .from('nyay_case_documents')
        .update({ consent_status: consentStatus, updated_at: new Date().toISOString() })
        .eq('id', attachmentId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .select('id')
      return Boolean(data && data.length > 0)
    },

    async listDrafts(ownerId: string, caseId: string) {
      const { data } = await admin
        .from('nyay_drafts')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: true })
      return data || []
    },

    async createDraft(ownerId, caseId, title, content, caseVersion) {
      const { data, error } = await admin
        .from('nyay_drafts')
        .insert({
          case_id: caseId,
          owner_id: ownerId,
          title,
          content,
          version: 1,
          case_version: caseVersion,
          status: 'preliminary',
        })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to create draft')
      return data
    },

    async updateDraft(ownerId, caseId, draftId, title, content, caseVersion, expectedVersion) {
      const { data: existing } = await admin
        .from('nyay_drafts')
        .select('*')
        .eq('id', draftId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      if (!existing) throw new Error('Draft not found')
      if (expectedVersion !== undefined && expectedVersion !== null && Number(existing.version) !== expectedVersion) {
        throw new Error('Draft version conflict')
      }
      const { data, error } = await admin
        .from('nyay_drafts')
        .update({
          title,
          content,
          version: Number(existing.version) + 1,
          case_version: caseVersion,
          status: 'preliminary',
          updated_at: new Date().toISOString(),
        })
        .eq('id', draftId)
        .eq('owner_id', ownerId)
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to update draft')
      return data
    },

    async listUserActions(ownerId: string, caseId: string) {
      const { data } = await admin
        .from('nyay_user_actions')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: true })
      return data || []
    },

    async addUserAction(ownerId, caseId, conversationId, title, status, notes) {
      const { data, error } = await admin
        .from('nyay_user_actions')
        .insert({
          case_id: caseId,
          conversation_id: conversationId,
          owner_id: ownerId,
          title,
          status,
          notes,
        })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to create user action')
      return data
    },

    async updateUserAction(ownerId, caseId, actionId, status, notes) {
      const patch: Record<string, unknown> = { status, updated_at: new Date().toISOString() }
      if (notes !== undefined && notes !== null) patch.notes = notes
      const { data } = await admin
        .from('nyay_user_actions')
        .update(patch)
        .eq('id', actionId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .select('*')
        .maybeSingle()
      return data || null
    },

    async listSubmissionSteps(ownerId: string, caseId: string) {
      const { data } = await admin
        .from('nyay_submission_steps')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: true })
      return data || []
    },

    async addSubmissionStep(ownerId, caseId, conversationId, targetChannel, step, draftId, receiptReference, notes) {
      const { data, error } = await admin
        .from('nyay_submission_steps')
        .insert({
          case_id: caseId,
          conversation_id: conversationId,
          owner_id: ownerId,
          target_channel: targetChannel,
          step,
          draft_id: draftId || null,
          receipt_reference: receiptReference || '',
          notes: notes || '',
        })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to record submission step')
      return data
    },

    async getSealedUserKey(ownerId: string) {
      const { data } = await admin
        .from('nyay_user_keys')
        .select('sealed_key, key_hint')
        .eq('owner_id', ownerId)
        .maybeSingle()
      return data || null
    },

    async saveSealedUserKey(ownerId: string, sealedKey: string, hint: string) {
      const { error } = await admin.from('nyay_user_keys').upsert(
        {
          owner_id: ownerId,
          sealed_key: sealedKey,
          key_hint: hint,
          updated_at: new Date().toISOString(),
        },
        { onConflict: 'owner_id' }
      )
      if (error) throw new Error(error.message)
    },

    async deleteSealedUserKey(ownerId: string) {
      await admin.from('nyay_user_keys').delete().eq('owner_id', ownerId)
    },

    async listVerifiedContacts(): Promise<VerifiedContactRecord[]> {
      const { data } = await admin
        .from('nyay_verified_contacts')
        .select('*')
        .eq('retired', false)
        .order('id', { ascending: true })
      return (data || []) as VerifiedContactRecord[]
    },

    async listEditorialItems(status?: string | null) {
      let q = admin.from('nyay_editorial_propositions').select('*')
      if (status) q = q.eq('status', status)
      const { data } = await q.order('updated_at', { ascending: false })
      return data || []
    },

    async submitEditorialProposal(ownerId: string, proposal: Record<string, unknown>) {
      const itemId = `ed-${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`
      const { data, error } = await admin
        .from('nyay_editorial_propositions')
        .insert({
          item_id: itemId,
          proposition_id: String(proposal.proposition_id),
          submitted_by: ownerId,
          status: 'pending_editorial_review',
          proposal,
        })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to submit editorial proposal')
      return data
    },

    async decideEditorialProposal(ownerId, itemId, decision, notes) {
      const { data: reviewer } = await admin
        .from('nyay_editorial_reviewers')
        .select('*')
        .eq('user_id', ownerId)
        .eq('active', true)
        .maybeSingle()
      if (!reviewer) {
        throw new Error('Editorial reviewer role required')
      }
      const { data, error } = await admin
        .from('nyay_editorial_propositions')
        .update({
          status: decision,
          decided_by: ownerId,
          decision: {
            reviewer_id: ownerId,
            reviewer_name: reviewer.reviewer_name,
            bar_enrollment_ref: reviewer.bar_enrollment_ref,
            decision,
            notes,
            decided_at: new Date().toISOString(),
          },
          updated_at: new Date().toISOString(),
        })
        .eq('item_id', itemId)
        .select('*')
        .maybeSingle()
      if (error) throw new Error(error.message)
      if (!data) throw new Error('Editorial item not found')
      return data
    },

    async restoreTransferredCase(ownerId: string, snapshot: Record<string, unknown>) {
      const convSnap = (snapshot.conversation || {}) as Record<string, unknown>
      const lang: Language =
        convSnap.language && ['en', 'hi', 'hinglish'].includes(String(convSnap.language))
          ? (String(convSnap.language) as Language)
          : 'en'
      const created = await this.createConversation(ownerId, lang, null)
      const caseId = String(created.case_id)
      const memSnap = (snapshot.case_memory || {}) as CaseMemoryModel
      await admin.from('nyay_case_memory').upsert(
        {
          case_id: caseId,
          owner_id: ownerId,
          version: Number(memSnap.version || 0),
          memory: memSnap,
          summary: String(snapshot.summary || ''),
        },
        { onConflict: 'case_id' }
      )
      for (const d of (snapshot.drafts as Array<Record<string, unknown>> | undefined) || []) {
        await this.createDraft(ownerId, caseId, String(d.title || 'Draft'), String(d.content || ''), Number(memSnap.version || 0))
      }
      return created
    },

    async admitTurn(params): Promise<AdmitTurnResult> {
      const { data, error } = await admin.rpc('nyay_admit_turn', {
        p_owner_id: params.ownerId,
        p_conversation_id: params.conversationId,
        p_request_id: params.requestId,
        p_payload_hash: params.payloadHash,
        p_user_content: params.userContent,
        p_lease_seconds: params.leaseSeconds ?? 90,
        ...(params.nowIso ? { p_now: params.nowIso } : {}),
      })
      if (error) throw new Error(error.message)
      return data as AdmitTurnResult
    },

    async appendTurnEvent(params) {
      const { data, error } = await admin.rpc('nyay_append_turn_event', {
        p_execution_id: params.executionId,
        p_owner_id: params.ownerId,
        p_lease_token: params.leaseToken,
        p_kind: params.kind,
        p_payload: params.payload,
        p_block_id: params.blockId ?? null,
        p_block_revision: params.blockRevision ?? 1,
        p_publication_status: params.publicationStatus ?? 'published',
      })
      if (error) throw new Error(error.message)
      return data as Record<string, unknown>
    },

    async commitTurn(params) {
      const { data, error } = await admin.rpc('nyay_commit_turn', {
        p_execution_id: params.executionId,
        p_owner_id: params.ownerId,
        p_lease_token: params.leaseToken,
        p_expected_case_version: params.expectedCaseVersion,
        p_new_case_version: params.newCaseVersion,
        p_memory: params.memory,
        p_summary: params.summary,
        p_staged_patches: params.stagedPatches,
        p_case_proposals: params.caseProposals,
        p_assistant_content: params.assistantContent,
        p_assistant_metadata: params.assistantMetadata,
        p_drafts: params.drafts,
        p_result: params.result,
      })
      if (error) throw new Error(error.message)
      return data as Record<string, unknown>
    },

    async updateCaseLifecycle(ownerId, caseId, patch) {
      const updates: Record<string, unknown> = { updated_at: new Date().toISOString() }
      if (patch.domain) updates.domain = patch.domain
      if (patch.incident_date !== undefined) updates.incident_date = patch.incident_date
      if (patch.jurisdiction) updates.jurisdiction = patch.jurisdiction
      if (patch.lifecycle_state) updates.lifecycle_state = patch.lifecycle_state
      const { data } = await admin
        .from('nyay_cases')
        .update(updates)
        .eq('id', caseId)
        .eq('owner_id', ownerId)
        .select('*')
        .maybeSingle()
      return data || null
    },

    async listProviderConnections(ownerId: string) {
      const { data } = await admin
        .from('nyay_provider_connections')
        .select('*')
        .eq('owner_id', ownerId)
        .order('provider', { ascending: true })
      return data || []
    },

    async upsertProviderConnection(params) {
      const nowIso = new Date().toISOString()
      const { data, error } = await admin
        .from('nyay_provider_connections')
        .upsert(
          {
            owner_id: params.ownerId,
            provider: params.provider,
            provider_account_email: params.providerAccountEmail,
            provider_user_id: params.providerUserId,
            granted_scopes: params.grantedScopes,
            status: 'connected',
            reply_monitoring_opted_in: Boolean(params.replyMonitoringOptedIn),
            last_verified_at: nowIso,
            revoked_at: null,
            updated_at: nowIso,
          },
          { onConflict: 'owner_id,provider' }
        )
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to save provider connection')
      await admin.from('nyay_provider_secrets').upsert(
        {
          connection_id: data.id,
          owner_id: params.ownerId,
          sealed_access_token: params.sealedAccessToken,
          sealed_refresh_token: params.sealedRefreshToken || null,
          token_expires_at: params.tokenExpiresAt || null,
          updated_at: nowIso,
        },
        { onConflict: 'connection_id' }
      )
      return data
    },

    async revokeProviderConnection(ownerId, provider) {
      const nowIso = new Date().toISOString()
      const { data: conn } = await admin
        .from('nyay_provider_connections')
        .update({ status: 'revoked', revoked_at: nowIso, updated_at: nowIso })
        .eq('owner_id', ownerId)
        .eq('provider', provider)
        .select('id')
        .maybeSingle()
      if (!conn) return false
      await admin.from('nyay_provider_secrets').delete().eq('connection_id', conn.id).eq('owner_id', ownerId)
      if (provider === 'google_drive') {
        await admin
          .from('nyay_drive_case_folders')
          .update({ sync_status: 'revoked', updated_at: nowIso })
          .eq('owner_id', ownerId)
        await admin
          .from('nyay_drive_manifests')
          .update({
            sync_status: 'revoked',
            status_explanation: 'Google Drive access was revoked by user.',
            updated_at: nowIso,
          })
          .eq('owner_id', ownerId)
      }
      return true
    },

    async setGmailReplyMonitoring(ownerId, optedIn) {
      const { data } = await admin
        .from('nyay_provider_connections')
        .update({ reply_monitoring_opted_in: optedIn, updated_at: new Date().toISOString() })
        .eq('owner_id', ownerId)
        .eq('provider', 'google_gmail')
        .select('*')
        .maybeSingle()
      return data || null
    },

    async getDriveCaseFolder(ownerId, caseId) {
      const { data } = await admin
        .from('nyay_drive_case_folders')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .maybeSingle()
      return (data as never) || null
    },

    async upsertDriveCaseFolder(params) {
      const nowIso = new Date().toISOString()
      const { data, error } = await admin
        .from('nyay_drive_case_folders')
        .upsert(
          {
            case_id: params.caseId,
            owner_id: params.ownerId,
            connection_id: params.connectionId,
            provider_account_email: params.providerAccountEmail,
            drive_folder_id: params.driveFolderId,
            opaque_folder_name: params.opaqueFolderName,
            sync_status: 'synced',
            updated_at: nowIso,
          },
          { onConflict: 'case_id,owner_id' }
        )
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to upsert Drive case folder')
      return data as never
    },

    async listDriveManifests(ownerId, caseId) {
      const { data } = await admin
        .from('nyay_drive_manifests')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: true })
      return (data || []) as never
    },

    async upsertDriveManifestItem(params) {
      const { data: existing } = await admin
        .from('nyay_drive_manifests')
        .select('*')
        .eq('owner_id', params.ownerId)
        .eq('case_id', params.caseId)
        .eq('sha256', params.sha256)
        .maybeSingle()
      if (existing) {
        return { item: existing as never, duplicate_reused: true }
      }
      const { data, error } = await admin
        .from('nyay_drive_manifests')
        .insert({
          case_id: params.caseId,
          owner_id: params.ownerId,
          folder_id: params.folderId,
          document_id: params.documentId || null,
          provider_account_email: params.providerAccountEmail,
          drive_file_id: params.driveFileId,
          filename: params.filename,
          mime_type: params.mimeType,
          byte_length: params.byteLength,
          sha256: params.sha256,
          evidence_type: params.evidenceType,
          provenance: params.provenance,
          sync_status: params.syncStatus,
          original_preserved: params.originalPreserved,
          web_view_link: params.webViewLink || null,
          status_explanation: params.statusExplanation,
        })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to save Drive manifest item')
      return { item: data as never, duplicate_reused: false }
    },

    async updateDriveManifestSyncStatus(params) {
      const { data } = await admin
        .from('nyay_drive_manifests')
        .update({
          sync_status: params.syncStatus,
          status_explanation: params.statusExplanation,
          last_reconciled_at: params.lastReconciledAt,
          updated_at: params.lastReconciledAt,
        })
        .eq('id', params.itemId)
        .eq('case_id', params.caseId)
        .eq('owner_id', params.ownerId)
        .select('id')
      return Boolean(data && data.length > 0)
    },

    async cleanupTemporaryDocumentText(ownerId, caseId) {
      const { data } = await admin
        .from('nyay_case_documents')
        .update({ extracted_text: '', updated_at: new Date().toISOString() })
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .eq('storage_mode', 'disclosed_temporary_processing')
        .select('id')
      return data ? data.length : 0
    },

    async listGmailEvidenceMessages(ownerId, caseId) {
      const { data } = await admin
        .from('nyay_gmail_evidence_messages')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: true })
      return (data || []) as never
    },

    async importGmailEvidenceMessage(params) {
      const { data, error } = await admin
        .from('nyay_gmail_evidence_messages')
        .upsert(
          {
            case_id: params.caseId,
            owner_id: params.ownerId,
            gmail_message_id: params.gmailMessageId,
            gmail_thread_id: params.gmailThreadId,
            provider_account_email: params.providerAccountEmail,
            sender: params.sender,
            recipient: params.recipient,
            subject: params.subject,
            snippet: params.snippet,
            body_text: params.bodyText,
            received_at: params.receivedAt || null,
            untrusted_instruction_flags: params.untrustedInstructionFlags,
          },
          { onConflict: 'case_id,owner_id,gmail_message_id' }
        )
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to import Gmail message')
      return data as never
    },

    async listGmailApprovals(ownerId, caseId) {
      const { data } = await admin
        .from('nyay_gmail_approvals')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: false })
      return (data || []) as never
    },

    async getGmailApproval(ownerId, caseId, approvalId) {
      const { data } = await admin
        .from('nyay_gmail_approvals')
        .select('*')
        .eq('id', approvalId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      return (data as never) || null
    },

    async createGmailApproval(params) {
      const { data, error } = await admin
        .from('nyay_gmail_approvals')
        .insert({
          case_id: params.caseId,
          conversation_id: params.conversationId,
          owner_id: params.ownerId,
          provider_account_email: params.providerAccountEmail,
          sender_email: params.senderEmail,
          to_recipients: params.toRecipients,
          cc_recipients: params.ccRecipients,
          bcc_recipients: params.bccRecipients,
          subject: params.subject,
          body: params.body,
          selected_attachment_ids: params.selectedAttachmentIds,
          reply_thread_id: params.replyThreadId || null,
          payload_hash: params.payloadHash,
          status: 'approved',
          expires_at: params.expiresAt,
        })
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to create Gmail approval')
      return data as never
    },

    async updateGmailApprovalStatus(ownerId, caseId, approvalId, status) {
      const { data } = await admin
        .from('nyay_gmail_approvals')
        .update({ status, updated_at: new Date().toISOString() })
        .eq('id', approvalId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .select('id')
      return Boolean(data && data.length > 0)
    },

    async listGmailDispatches(ownerId, caseId) {
      const { data } = await admin
        .from('nyay_gmail_dispatches')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('case_id', caseId)
        .order('created_at', { ascending: false })
      return (data || []) as never
    },

    async getGmailDispatchByApproval(ownerId, caseId, approvalId) {
      const { data } = await admin
        .from('nyay_gmail_dispatches')
        .select('*')
        .eq('approval_id', approvalId)
        .eq('case_id', caseId)
        .eq('owner_id', ownerId)
        .maybeSingle()
      return (data as never) || null
    },

    async upsertGmailDispatch(params) {
      const nowIso = new Date().toISOString()
      const { data, error } = await admin
        .from('nyay_gmail_dispatches')
        .upsert(
          {
            approval_id: params.approvalId,
            case_id: params.caseId,
            owner_id: params.ownerId,
            payload_hash: params.payloadHash,
            provider_account_email: params.providerAccountEmail,
            dispatch_status: params.dispatchStatus,
            gmail_message_id: params.gmailMessageId || null,
            gmail_thread_id: params.gmailThreadId || null,
            event_classification: 'provider_email_sent_not_official_registration',
            reconciliation_notes: params.reconciliationNotes || '',
            updated_at: nowIso,
          },
          { onConflict: 'approval_id' }
        )
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to upsert Gmail dispatch')
      return data as never
    },

    async listLegalProvisions(domain) {
      let q = admin.from('nyay_legal_provisions').select('*')
      if (domain) q = q.eq('domain', domain)
      const { data } = await q.order('provision_id', { ascending: true })
      return data || []
    },

    async invalidateLegalProvisionCache(provisionId, reviewState = 'amended_cache_invalidated') {
      const { data: existing } = await admin
        .from('nyay_legal_provisions')
        .select('cache_epoch')
        .eq('provision_id', provisionId)
        .maybeSingle()
      if (!existing) return null
      const { data } = await admin
        .from('nyay_legal_provisions')
        .update({
          review_state: reviewState,
          cache_epoch: Number(existing.cache_epoch || 1) + 1,
          last_checked_at: new Date().toISOString(),
        })
        .eq('provision_id', provisionId)
        .select('*')
        .maybeSingle()
      return data || null
    },

    async getUsageBudget(ownerId) {
      const todayDate = new Date().toISOString().slice(0, 10)
      const { data } = await admin
        .from('nyay_usage_budgets')
        .select('*')
        .eq('owner_id', ownerId)
        .eq('window_date', todayDate)
        .maybeSingle()
      return data || null
    },

    async recordUsageBudget(params) {
      const todayDate = new Date().toISOString().slice(0, 10)
      const existing = await this.getUsageBudget?.(params.ownerId)
      const nextRequests = Number(existing?.requests_count || 0) + params.requestsDelta
      const nextProviderCalls = Number(existing?.provider_calls_count || 0) + params.providerCallsDelta
      const nextTokens = Number(existing?.total_tokens_used || 0) + params.tokensDelta
      const nextSpend = Number((Number(existing?.estimated_spend_usd || 0) + params.spendUsdDelta).toFixed(4))
      const { data, error } = await admin
        .from('nyay_usage_budgets')
        .upsert(
          {
            owner_id: params.ownerId,
            window_date: todayDate,
            requests_count: nextRequests,
            provider_calls_count: nextProviderCalls,
            total_tokens_used: nextTokens,
            estimated_spend_usd: nextSpend,
            updated_at: new Date().toISOString(),
          },
          { onConflict: 'owner_id,window_date' }
        )
        .select('*')
        .single()
      if (error || !data) throw new Error(error?.message || 'Failed to record usage budget')
      return data
    },
  }
}

if (typeof Deno !== 'undefined' && typeof Deno.serve === 'function') {
  const supabaseUrl = Deno.env.get('SUPABASE_URL') || ''
  const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || ''
  const anonKey = Deno.env.get('SUPABASE_ANON_KEY') || ''
  const serverOpenAiKey = Deno.env.get('OPENAI_API_KEY') || Deno.env.get('OPENAI_KEY') || null
  const byokMasterSecret = Deno.env.get('NYAY_BYOK_MASTER_SECRET') || serviceRoleKey || 'nyay-edge-byok-secret'

  const db = createSupabaseDatabaseAdapter(supabaseUrl, serviceRoleKey, anonKey)
  const provider = new OpenAiResponsesProvider({
    chatModel: Deno.env.get('OPENAI_CHAT_MODEL') || 'gpt-4o',
    reviewModel: Deno.env.get('OPENAI_REVIEW_MODEL') || 'gpt-4o',
  })

  const handler = createNyayApiHandler({
    db,
    provider,
    config: {
      serverOpenAiKey,
      byokMasterSecret,
      region: Deno.env.get('SB_REGION') || 'ap-northeast-1',
      allowedOrigins: ['https://nyay-sathi-sage.vercel.app', 'https://localhost', 'http://localhost:5173'],
    },
  })

  const enabled = Deno.env.get('NYAY_RESUMABLE_ENABLED') === 'true'
  const runtime=runtimeConfig({
    model:Deno.env.get('NYAY_AGENT_MODEL') || DEFAULT_RUNTIME.model,
    reasoning:Deno.env.get('NYAY_AGENT_REASONING') || DEFAULT_RUNTIME.reasoning,
    maxOutputTokens:Number(Deno.env.get('NYAY_AGENT_MAX_OUTPUT_TOKENS') || DEFAULT_RUNTIME.maxOutputTokens),
  })
  const resumeKey = enabled ? (Deno.env.get('NYAY_RESUMABLE_OPENAI_KEY') || serverOpenAiKey || '') : ''
  const admin = createClient(supabaseUrl, serviceRoleKey, {
    auth: {persistSession:false, autoRefreshToken:false},
    global: {fetch: (input, init) => fetch(input, {
      ...init, signal: init?.signal ? AbortSignal.any([init.signal,AbortSignal.timeout(4_000)]) : AbortSignal.timeout(4_000),
    })},
  })
  const checked = <T>(response: {data:T; error:unknown}):T => {
    if (response.error) throw new Error('Database operation failed')
    return response.data
  }
  const embeddingUrl = Deno.env.get('NYAY_LEGAL_EMBEDDING_URL') || ''
  const embeddingKey = Deno.env.get('NYAY_LEGAL_EMBEDDING_KEY') || ''
  const openAiEmbeddingKey = Deno.env.get('OPENAI_EMBEDDING_API_KEY') || serverOpenAiKey || ''
  let embedder: ReturnType<typeof createVersionedQueryEmbedder> | null = null
  if (openAiEmbeddingKey && LEGAL_CORPUS_COVERAGE_DECLARATION.embeddingModel.startsWith('text-embedding-')) {
    try {
      embedder = createOpenAiQueryEmbedder(openAiEmbeddingKey)
    } catch {
      console.warn(JSON.stringify({type:'nyay.legal.openai_embedding_config_invalid'}))
    }
  } else if (embeddingUrl && embeddingKey) {
    try {
      embedder = createVersionedQueryEmbedder(embeddingUrl,embeddingKey)
    } catch {
      console.warn(JSON.stringify({type:'nyay.legal.embedding_config_invalid'}))
    }
  }
  const retrieve = createRequiredSemanticRetriever({
    embedder,
    async rpc(name,args,signal) {
      return checked(await admin.rpc(name,args).abortSignal(signal)) as SupabaseHybridRpcRow[]
    },
    async fetchPassagesByIds(ids,signal) {
      return checked(await admin.from('nyay_legal_passages')
        .select('passage_id,document_id,title,text,locator,official_url,authority,region,valid_from,valid_until,date_independent,version,acquired_at,review_state,limitations,related_passage_ids')
        .eq('review_state','approved')
        .eq('embedding_model',LEGAL_CORPUS_COVERAGE_DECLARATION.embeddingModel)
        .eq('embedding_version',LEGAL_CORPUS_COVERAGE_DECLARATION.embeddingVersion)
        .in('passage_id',ids).abortSignal(signal)) as SupabaseHybridRpcRow[]
    },
  })
  const resumable = createResumableHandler({
    key:resumeKey,
    admissionsPaused:!embedder || Deno.env.get('NYAY_PAUSE_TURN_ADMISSION')==='true',
    scheduleSecret:enabled ? (Deno.env.get('NYAY_WORKER_SECRET') || '') : '',
    webhookSecret:enabled ? (Deno.env.get('NYAY_OPENAI_WEBHOOK_SECRET') || '') : '',
    provider:new OpenAiBackgroundProvider(runtime),
    runtime,
    retrieve,
    authenticate:db.authenticate,
    rpc:async <T>(name:string,args?:Record<string,unknown>) => checked(await admin.rpc(name,args)) as T,
    async read(owner,chat,requestId) {
      let query=admin.from('nyay_turn_executions')
        .select('id,request_id,status,result,error_detail')
        .eq('owner_id',owner).eq('conversation_id',chat)
      if(requestId) query=query.eq('request_id',requestId)
      else query=query.in('status',['queued','running','reviewed'])
      const row=checked(await query.maybeSingle())
      return row ? {...row,execution_id:row.id} : null
    },
    async events(owner,id,after) {
      return checked(await admin.from('nyay_turn_events')
        .select('seq,kind,payload,execution_id,request_id,block_id')
        .eq('owner_id',owner).eq('execution_id',id).eq('publication_status','published')
        .gt('seq',after).order('seq').limit(100)) || []
    },
    async prepare(job) {
      const turn=checked(await admin.from('nyay_turn_executions').select('conversation_id,request_id')
        .eq('id',job.execution_id).eq('owner_id',job.owner_id).single())
      if(!turn) throw new Error('Missing turn')
      const chat=checked(await admin.from('nyay_conversations').select('case_id')
        .eq('id',turn.conversation_id).eq('owner_id',job.owner_id).single())
      if(!chat) throw new Error('Missing conversation')
      const caseId=chat.case_id
      const selectedIds=job.checkpoint.input.attachment_ids
      const [caseResult, memoryResult, historyResult, docsResult, safetyResult]=await Promise.all([
        admin.from('nyay_cases').select('jurisdiction,incident_date').eq('id',caseId).eq('owner_id',job.owner_id).single(),
        admin.from('nyay_case_memory').select('memory,version,summary,staged_patches,case_proposals,quality_review_consent')
          .eq('case_id',caseId).eq('owner_id',job.owner_id).maybeSingle(),
        admin.from('nyay_messages').select('id,content').eq('conversation_id',turn.conversation_id)
          .eq('owner_id',job.owner_id).eq('role','user').neq('request_id',turn.request_id)
          .order('created_at',{ascending:false}).limit(3),
        selectedIds.length ? admin.from('nyay_case_documents').select('id,filename,extracted_text,consent_status')
          .eq('case_id',caseId).eq('owner_id',job.owner_id).eq('consent_status','consented').in('id',selectedIds)
          : Promise.resolve({data:[],error:null}),
        admin.from('nyay_turn_events').select('payload,nyay_turn_executions!inner(conversation_id)')
          .eq('owner_id',job.owner_id).eq('kind','safety')
          .eq('nyay_turn_executions.conversation_id',turn.conversation_id)
          .order('created_at',{ascending:false}).limit(5),
      ])
      const caseRow=checked(caseResult)
      if(!caseRow) throw new Error('Missing case')
      const input=job.checkpoint.input
      const memoryRow=checked(memoryResult)
      const version=memoryRow?.version || 0
      const memory={
        version, memory:normalizeCaseMemory(memoryRow?.memory,version),summary:memoryRow?.summary || '',
        staged_patches:memoryRow?.staged_patches || [],case_proposals:memoryRow?.case_proposals || [],
        quality_review_consent:Boolean(memoryRow?.quality_review_consent),
      }
      return {
        memory, requestId:turn.request_id,
        region:caseRow.jurisdiction==='India' ? null : caseRow.jurisdiction,
        incidentDate:caseRow.incident_date,asOfDate:new Date().toISOString().slice(0,10),
        priorMessages:(checked(historyResult) || []).reverse().map(m=>({...m,content:m.content.slice(0,1600)})),
        attachments:(checked(docsResult) || []).map(d=>({...d,extracted_text:d.extracted_text.slice(0,2500)})),
        ...await prepareSafety(input.content,input.language,memory.memory,
          (checked(safetyResult) || []).map(e=>e.payload)),
      }
    },
  },handler)
  Deno.serve(resumable)
}
