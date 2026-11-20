// Package 5: User-Owned Google Drive Case Folder & Evidence Manifest Adapter.
// Pure TypeScript, zero Node-only dependencies (compatible with Deno 2 and Vitest).

import { sha256Hex } from './crypto.ts'

export const REQUIRED_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
export const FORBIDDEN_BROAD_DRIVE_SCOPES = [
  'https://www.googleapis.com/auth/drive',
  'https://www.googleapis.com/auth/drive.readonly',
]

export type DriveSyncStatus = 'synced' | 'moved' | 'deleted' | 'revoked' | 'local_only'

export type DriveEvidenceProvenance =
  | 'user_uploaded_original'
  | 'user_selected_drive_file'
  | 'local_v2_disclosed_explicit'

export interface DriveCaseFolderRecord {
  id: string
  case_id: string
  owner_id: string
  connection_id: string
  provider_account_email: string
  drive_folder_id: string
  opaque_folder_name: string
  sync_status: 'synced' | 'moved' | 'deleted' | 'revoked'
  created_at: string
  updated_at: string
}

export interface DriveManifestItem {
  id: string
  case_id: string
  owner_id: string
  folder_id: string | null
  document_id?: string | null
  provider_account_email: string
  drive_file_id: string
  filename: string
  mime_type: string
  byte_length: number
  sha256: string
  evidence_type: string
  provenance: DriveEvidenceProvenance
  sync_status: DriveSyncStatus
  original_preserved: boolean
  web_view_link?: string | null
  status_explanation: string
  last_reconciled_at: string
  created_at: string
  updated_at: string
}

/**
 * Generates an opaque, disclosure-minimizing case folder name for Google Drive.
 * Never embeds sensitive dispute titles, opponent names, or criminal/fraud labels in Drive folder names.
 */
export async function buildOpaqueCaseFolderName(caseId: string, ownerId: string): Promise<string> {
  const digest = await sha256Hex(`nyay-drive-folder-v1:${ownerId}:${caseId}`)
  return `NyaySaathi-Case-${digest.slice(0, 12)}`
}

/**
 * Validates that a Google Drive connection requests only the narrowest suitable scope (`drive.file`)
 * and rejects overly broad full-Drive access scopes.
 */
export function validateDriveScopes(scopes: string[]): { valid: boolean; reason?: string } {
  const normalized = (scopes || []).map(s => s.trim()).filter(Boolean)
  if (!normalized.includes(REQUIRED_DRIVE_SCOPE)) {
    return {
      valid: false,
      reason: `Google Drive integration requires the narrow '${REQUIRED_DRIVE_SCOPE}' scope.`,
    }
  }
  for (const forbidden of FORBIDDEN_BROAD_DRIVE_SCOPES) {
    if (normalized.includes(forbidden)) {
      return {
        valid: false,
        reason: `Overly broad scope '${forbidden}' is not permitted; use '${REQUIRED_DRIVE_SCOPE}' only.`,
      }
    }
  }
  return { valid: true }
}

/**
 * Explains missing, moved, deleted, or revoked Drive files truthfully to the user.
 */
export function explainDriveSyncStatus(status: DriveSyncStatus, filename: string, accountEmail: string): string {
  switch (status) {
    case 'synced':
      return `Original file "${filename}" is preserved in your Google Drive (${accountEmail}) with verified SHA-256 hash.`
    case 'moved':
      return `File "${filename}" was moved outside the case folder in Google Drive (${accountEmail}). Its hash and manifest reference remain intact.`
    case 'deleted':
      return `File "${filename}" is no longer found in Google Drive (${accountEmail}) (moved to Trash or deleted). Re-upload or select the original before relying on it in a filing.`
    case 'revoked':
      return `Google Drive access for ${accountEmail} was disconnected or revoked. Private extracted notes remain protected, but Drive originals cannot be synced until reconnected.`
    case 'local_only':
      return `File "${filename}" is stored in disclosed temporary processing mode only and has not been migrated to Google Drive.`
  }
}

/**
 * Reconciles a case's Drive manifest items against observed provider file states
 * without automatically deleting case evidence records or silently migrating local V2 files.
 */
export function reconcileDriveManifestItems(params: {
  items: DriveManifestItem[]
  providerFileStates: Record<string, 'present' | 'moved' | 'trashed' | 'missing'>
  connectionStatus: 'connected' | 'expired' | 'revoked' | 'error'
  nowIso?: string
}): {
  updatedItems: Array<{
    id: string
    drive_file_id: string
    sync_status: DriveSyncStatus
    status_explanation: string
    last_reconciled_at: string
  }>
  summary: {
    synced: number
    moved: number
    deleted: number
    revoked: number
    local_only: number
  }
} {
  const nowIso = params.nowIso || new Date().toISOString()
  const summary = { synced: 0, moved: 0, deleted: 0, revoked: 0, local_only: 0 }
  const updatedItems: Array<{
    id: string
    drive_file_id: string
    sync_status: DriveSyncStatus
    status_explanation: string
    last_reconciled_at: string
  }> = []

  for (const item of params.items) {
    let nextStatus: DriveSyncStatus = item.sync_status
    if (item.sync_status === 'local_only') {
      nextStatus = 'local_only'
    } else if (params.connectionStatus === 'revoked' || params.connectionStatus === 'expired') {
      nextStatus = 'revoked'
    } else {
      const providerState = params.providerFileStates[item.drive_file_id]
      if (providerState === 'present') nextStatus = 'synced'
      else if (providerState === 'moved') nextStatus = 'moved'
      else if (providerState === 'trashed' || providerState === 'missing') nextStatus = 'deleted'
      else nextStatus = item.sync_status
    }
    summary[nextStatus]++
    updatedItems.push({
      id: item.id,
      drive_file_id: item.drive_file_id,
      sync_status: nextStatus,
      status_explanation: explainDriveSyncStatus(nextStatus, item.filename, item.provider_account_email),
      last_reconciled_at: nowIso,
    })
  }

  return { updatedItems, summary }
}
