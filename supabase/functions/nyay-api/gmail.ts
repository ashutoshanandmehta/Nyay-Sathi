// Package 6: Gmail Scoped Evidence Search, Editable Review, Payload-Bound Approvals & Dispatch Reconciliation.
// Pure TypeScript, zero Node-only dependencies (compatible with Deno 2 and Vitest).

import { canonicalPayloadHash } from './crypto.ts'

export const GMAIL_READ_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
export const GMAIL_SEND_SCOPE = 'https://www.googleapis.com/auth/gmail.send'

export interface GmailEvidenceMessageRecord {
  id: string
  case_id: string
  owner_id: string
  gmail_message_id: string
  gmail_thread_id: string
  provider_account_email: string
  sender: string
  recipient: string
  subject: string
  snippet: string
  body_text: string
  received_at: string | null
  untrusted_instruction_flags: string[]
  created_at: string
}

export interface GmailApprovalPayloadInput {
  owner_id: string
  case_id: string
  provider_account_email: string
  sender_email: string
  to_recipients: string[]
  cc_recipients?: string[]
  bcc_recipients?: string[]
  subject: string
  body: string
  selected_attachment_ids?: string[]
  reply_thread_id?: string | null
}

export interface GmailApprovalRecord {
  id: string
  case_id: string
  conversation_id: string
  owner_id: string
  provider_account_email: string
  sender_email: string
  to_recipients: string[]
  cc_recipients: string[]
  bcc_recipients: string[]
  subject: string
  body: string
  selected_attachment_ids: string[]
  reply_thread_id: string | null
  payload_hash: string
  version: number
  status: 'approved' | 'invalidated' | 'dispatched' | 'expired'
  expires_at: string
  created_at: string
  updated_at: string
}

export type GmailDispatchStatus =
  | 'dispatching'
  | 'sent_confirmed'
  | 'ambiguous_timeout_needs_reconciliation'
  | 'reconciled_sent'
  | 'reconciled_not_sent'
  | 'failed'

export interface GmailDispatchRecord {
  id: string
  approval_id: string
  case_id: string
  owner_id: string
  payload_hash: string
  provider_account_email: string
  dispatch_status: GmailDispatchStatus
  gmail_message_id: string | null
  gmail_thread_id: string | null
  event_classification: 'provider_email_sent_not_official_registration'
  reconciliation_notes: string
  created_at: string
  updated_at: string
}

export function validateGmailScopes(
  grantedScopes: string[],
  operation: 'search_read' | 'send'
): { valid: boolean; required_scope: string; reason?: string } {
  const scopes = new Set((grantedScopes || []).map(s => s.trim()))
  if (operation === 'search_read') {
    if (!scopes.has(GMAIL_READ_SCOPE)) {
      return {
        valid: false,
        required_scope: GMAIL_READ_SCOPE,
        reason: `Gmail evidence search/import requires '${GMAIL_READ_SCOPE}' permission.`,
      }
    }
    return { valid: true, required_scope: GMAIL_READ_SCOPE }
  }
  if (!scopes.has(GMAIL_SEND_SCOPE)) {
    return {
      valid: false,
      required_scope: GMAIL_SEND_SCOPE,
      reason: `Gmail reviewed send requires separate '${GMAIL_SEND_SCOPE}' permission.`,
    }
  }
  return { valid: true, required_scope: GMAIL_SEND_SCOPE }
}

const MALICIOUS_EMAIL_PATTERNS: Array<[string, RegExp]> = [
  [
    'prompt_override_attempt',
    /\b(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|system\s+prompt|you\s+are\s+now\s+an?\s+unrestricted|disregard\s+safety)\b/i,
  ],
  [
    'recipient_hijack_attempt',
    /\b(?:change\s+(?:the\s+)?recipient\s+to|forward\s+(?:all\s+)?(?:emails?|attachments?|documents?|case\s+files?)\s+to|bcc\s+all\s+to|send\s+copy\s+to\s+\S+@\S+)\b/i,
  ],
  [
    'tool_or_permission_escalation_attempt',
    /\b(?:grant\s+(?:full\s+)?access|enable\s+auto[- ]?send|bypass\s+approval|execute\s+tool|attach\s+all\s+files\s+automatically)\b/i,
  ],
]

/**
 * Scans untrusted email correspondence for embedded prompt-injection or recipient/tool hijack instructions.
 * Imported emails remain passive evidence data and can never alter recipients, tools, or permissions.
 */
export function scanEmailForUntrustedInstructions(
  subject: string,
  bodyText: string
): { flags: string[]; isUntrustedFlagged: boolean } {
  const combined = `${subject || ''}\n${bodyText || ''}`
  const flags: string[] = []
  for (const [flagName, regex] of MALICIOUS_EMAIL_PATTERNS) {
    if (regex.test(combined)) {
      flags.push(flagName)
    }
  }
  return {
    flags,
    isUntrustedFlagged: flags.length > 0,
  }
}

export function normalizeEmailList(list?: string[]): string[] {
  if (!Array.isArray(list)) return []
  return list
    .map(item => String(item || '').trim().toLowerCase())
    .filter(item => item.length >= 3 && item.includes('@'))
}

/**
 * Computes the versioned immutable payload hash binding sender, To/Cc/Bcc, subject, full body,
 * explicitly selected attachment IDs (never defaulting to all attachments), user, case, and provider identity.
 */
export async function computeGmailApprovalPayloadHash(input: GmailApprovalPayloadInput): Promise<string> {
  const canonical = {
    schema: 'nyay.gmail.approval.v1',
    owner_id: input.owner_id.trim(),
    case_id: input.case_id.trim(),
    provider_account_email: input.provider_account_email.trim().toLowerCase(),
    sender_email: input.sender_email.trim().toLowerCase(),
    to_recipients: normalizeEmailList(input.to_recipients),
    cc_recipients: normalizeEmailList(input.cc_recipients),
    bcc_recipients: normalizeEmailList(input.bcc_recipients),
    subject: input.subject,
    body: input.body,
    selected_attachment_ids: Array.isArray(input.selected_attachment_ids)
      ? [...input.selected_attachment_ids].map(id => String(id).trim()).filter(Boolean).sort()
      : [],
    reply_thread_id: input.reply_thread_id ? String(input.reply_thread_id).trim() : null,
  }
  return canonicalPayloadHash(canonical)
}

/**
 * Verifies that a send request has a current, unexpired, payload-matching approval
 * for the exact user, case, provider account, recipients, subject, body, and selected attachments.
 */
export async function verifyGmailApprovalForDispatch(params: {
  approval: GmailApprovalRecord
  requestPayload: GmailApprovalPayloadInput
  existingDispatch?: GmailDispatchRecord | null
  nowIso?: string
}): Promise<{
  valid: boolean
  code?:
    | 'APPROVAL_OWNERSHIP_MISMATCH'
    | 'APPROVAL_EXPIRED'
    | 'APPROVAL_ALREADY_INVALIDATED'
    | 'APPROVAL_ALREADY_DISPATCHED'
    | 'AMBIGUOUS_SEND_REQUIRES_RECONCILIATION'
    | 'APPROVAL_PAYLOAD_MISMATCH'
  detail?: string
  computed_hash: string
}> {
  const nowMs = new Date(params.nowIso || new Date().toISOString()).getTime()
  const computedHash = await computeGmailApprovalPayloadHash(params.requestPayload)

  if (
    params.approval.owner_id !== params.requestPayload.owner_id ||
    params.approval.case_id !== params.requestPayload.case_id ||
    params.approval.provider_account_email.toLowerCase() !==
      params.requestPayload.provider_account_email.trim().toLowerCase()
  ) {
    return {
      valid: false,
      code: 'APPROVAL_OWNERSHIP_MISMATCH',
      detail: 'Approval does not match the current user, case, or connected Gmail account.',
      computed_hash: computedHash,
    }
  }

  if (params.existingDispatch) {
    if (params.existingDispatch.dispatch_status === 'ambiguous_timeout_needs_reconciliation') {
      return {
        valid: false,
        code: 'AMBIGUOUS_SEND_REQUIRES_RECONCILIATION',
        detail:
          'A prior send attempt timed out ambiguously. Reconcile Gmail sent status before attempting another send to prevent duplicate emails.',
        computed_hash: computedHash,
      }
    }
    if (
      params.existingDispatch.dispatch_status === 'sent_confirmed' ||
      params.existingDispatch.dispatch_status === 'reconciled_sent'
    ) {
      return {
        valid: false,
        code: 'APPROVAL_ALREADY_DISPATCHED',
        detail: 'This approved email has already been sent and confirmed.',
        computed_hash: computedHash,
      }
    }
  }

  if (params.approval.status === 'invalidated') {
    return {
      valid: false,
      code: 'APPROVAL_ALREADY_INVALIDATED',
      detail: 'This approval was invalidated by an edit. Review and create a new approval.',
      computed_hash: computedHash,
    }
  }

  if (params.approval.status === 'dispatched') {
    return {
      valid: false,
      code: 'APPROVAL_ALREADY_DISPATCHED',
      detail: 'This approval has already been used.',
      computed_hash: computedHash,
    }
  }

  if (new Date(params.approval.expires_at).getTime() <= nowMs || params.approval.status === 'expired') {
    return {
      valid: false,
      code: 'APPROVAL_EXPIRED',
      detail: 'This send approval has expired. Please review the email and approve again.',
      computed_hash: computedHash,
    }
  }

  if (params.approval.payload_hash !== computedHash) {
    return {
      valid: false,
      code: 'APPROVAL_PAYLOAD_MISMATCH',
      detail:
        'Material edit detected in recipients, subject, body, or selected attachments. Approval is invalidated; please review and re-approve the exact payload.',
      computed_hash: computedHash,
    }
  }

  return {
    valid: true,
    computed_hash: computedHash,
  }
}
