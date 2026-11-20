import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ExternalLink,
  FolderArchive,
  FolderPlus,
  Mail,
  MessageSquarePlus,
  PhoneCall,
  RefreshCw,
  Scale,
  Send,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type {
  Attachment,
  CaseRecord,
  Conversation,
  Draft,
  DriveFolderInfo,
  DriveManifestRecord,
  GmailApproval,
  GmailDispatch,
  GmailEvidenceMessage,
  GoogleProviderConnection,
  Language,
  VerifiedContact,
} from '../types'

export type HomeActionIntent = 'know_my_rights' | 'resolve_complaint' | 'report_fraud'

export function ThreeActionHome({
  onSelectPrompt,
  onOpenMyCases,
}: {
  onSelectPrompt: (prompt: string) => void
  onOpenMyCases?: () => void
}) {
  const [selectedIntent, setSelectedIntent] = useState<HomeActionIntent | null>(null)

  const intentPrompts: Record<HomeActionIntent, { title: string; subtitle: string; prompts: string[] }> = {
    know_my_rights: {
      title: 'Know My Rights — Direct Legal Information',
      subtitle: 'Ask a general question right away. No complaint intake or Google account connection required.',
      prompts: [
        'What are my rights if police refuse to register an FIR?',
        'How does the 1 July 2024 transition from IPC/CrPC to BNS/BNSS work?',
        'Within how many hours must an e-commerce grievance officer acknowledge a complaint?',
      ],
    },
    resolve_complaint: {
      title: 'Resolve a Complaint — Consumer, Refund, Defective Goods & Banking',
      subtitle: 'Organize chronology, check evidence, and prepare a factual grievance or escalation draft.',
      prompts: [
        'My return was picked up 10 days ago, support closed my ticket, and my refund has not arrived.',
        'I received a defective appliance and the seller is refusing replacement or warranty repair.',
        'My UPI transaction failed and money was debited from my bank account without reversal after T+1 day.',
      ],
    },
    report_fraud: {
      title: 'Report Financial Fraud — Emergency Freeze & 1930 Action',
      subtitle:
        'Bypasses routine merchant waiting periods. Prioritizes immediate bank channel block, 1930 helpline, and cybercrime.gov.in reporting.',
      prompts: [
        'Money was just debited from my bank account via an unauthorized UPI / phishing link — what do I do right now?',
        'Someone tricked me into sharing an OTP and transferred money from my account 20 minutes ago.',
        'My digital wallet and net-banking credentials are compromised and debits are happening right now.',
      ],
    },
  }

  return (
    <section className="three-action-home" aria-label="Primary assistant pathways">
      <div className="three-action-grid">
        <button
          type="button"
          className={`three-action-card ${selectedIntent === 'know_my_rights' ? 'active' : ''}`}
          onClick={() => setSelectedIntent(selectedIntent === 'know_my_rights' ? null : 'know_my_rights')}
        >
          <BookOpen size={18} aria-hidden="true" />
          <div>
            <b>Know My Rights</b>
            <small>Ask any general legal question directly without intake</small>
          </div>
        </button>

        <button
          type="button"
          className={`three-action-card ${selectedIntent === 'resolve_complaint' ? 'active' : ''}`}
          onClick={() => setSelectedIntent(selectedIntent === 'resolve_complaint' ? null : 'resolve_complaint')}
        >
          <Scale size={18} aria-hidden="true" />
          <div>
            <b>Resolve a Complaint</b>
            <small>Refunds, defective products, service & failed payment disputes</small>
          </div>
        </button>

        <button
          type="button"
          className={`three-action-card fraud-urgent ${selectedIntent === 'report_fraud' ? 'active' : ''}`}
          onClick={() => setSelectedIntent(selectedIntent === 'report_fraud' ? null : 'report_fraud')}
        >
          <ShieldAlert size={18} aria-hidden="true" />
          <div>
            <b>Report Financial Fraud</b>
            <small>Immediate 1930 / cybercrime.gov.in & bank channel block</small>
          </div>
        </button>
      </div>

      {onOpenMyCases && (
        <div className="workspace-inline-row" style={{ marginTop: '0.5rem' }}>
          <span className="muted">Continuing an earlier dispute?</span>
          <button type="button" className="text-action" onClick={onOpenMyCases}>
            Open My Cases →
          </button>
        </div>
      )}

      {selectedIntent && (
        <div className="intent-drawer-card" role="region" aria-label={intentPrompts[selectedIntent].title}>
          <b>{intentPrompts[selectedIntent].title}</b>
          <p className="muted">{intentPrompts[selectedIntent].subtitle}</p>
          <div className="intent-prompt-list">
            {intentPrompts[selectedIntent].prompts.map(p => (
              <button
                key={p}
                type="button"
                className="workspace-btn"
                onClick={() => onSelectPrompt(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

export function MyCasesPanel({
  conversations,
  activeConversationId,
  language,
  onSelectConversation,
  onNewChatInCase,
}: {
  conversations: Conversation[]
  activeConversationId: string
  language: Language
  onSelectConversation: (conversationId: string) => void
  onNewChatInCase: (caseId: string, language: Language) => Promise<void>
}) {
  const [cases, setCases] = useState<CaseRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [busyCaseId, setBusyCaseId] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    api
      .listCases()
      .then(res => {
        if (mounted) setCases(res)
      })
      .catch(() => {
        if (mounted) setCases([])
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [conversations])

  // Group conversations by case_id (or conversation.id if legacy backend without case_id)
  const grouped = new Map<string, { caseRecord?: CaseRecord; chats: Conversation[] }>()
  for (const c of cases) {
    grouped.set(c.id, { caseRecord: c, chats: [] })
  }
  for (const conv of conversations) {
    const cid = conv.case_id || conv.id
    const existing = grouped.get(cid)
    if (existing) {
      existing.chats.push(conv)
    } else {
      grouped.set(cid, {
        caseRecord: {
          id: cid,
          title: conv.title,
          status: 'intake',
          domain: conv.domain || 'unknown',
          created_at: conv.created_at,
          updated_at: conv.updated_at,
        },
        chats: [conv],
      })
    }
  }

  return (
    <div className="panel-content my-cases-panel">
      <p className="muted">
        Cases are maintained independently of individual chats. You can reopen any case with a new conversation while
        keeping its facts, documents, and drafts intact.
      </p>
      {loading && <p className="muted">Loading your cases…</p>}
      {!loading && grouped.size === 0 && <p className="muted">No saved cases yet.</p>}
      {Array.from(grouped.entries()).map(([caseId, entry]) => {
        const title = entry. chats[0]?.title || entry.caseRecord?.title || 'Case'
        const domain = entry.caseRecord?.domain || entry.chats[0]?.domain || 'general'
        const status = entry.caseRecord?.status || 'intake'
        const lifecycle = entry.caseRecord?.lifecycle_state
        return (
          <section className="knowledge-card" key={caseId} style={{ marginBottom: '0.75rem' }}>
            <div className="workspace-inline-row">
              <b>{title}</b>
              <small className="fact-badge">{domain.replaceAll('_', ' ')} · {status}</small>
            </div>
            <small className="muted">Case ID: {caseId.slice(0, 8)} · {entry.chats.length} chat(s)</small>
            {lifecycle && (
              <p className="muted" style={{ fontSize: '0.8rem', marginTop: '0.35rem' }}>
                Submissions: {lifecycle.submissions?.length || 0} · Promises: {lifecycle.promises?.length || 0} ·
                Processed refund claims: {lifecycle.processed_refunds?.length || 0} · Remedy received:{' '}
                {lifecycle.remedy_receipt ? 'Confirmed' : 'Not yet confirmed'} · Status: {lifecycle.closure || 'open'}
              </p>
            )}
            <div className="workspace-stack" style={{ marginTop: '0.5rem' }}>
              {entry.chats.map(chat => (
                <button
                  key={chat.id}
                  type="button"
                  className={`workspace-btn ${chat.id === activeConversationId ? 'active' : ''}`}
                  onClick={() => onSelectConversation(chat.id)}
                >
                  Open chat: {chat.title} ({chat.language.toUpperCase()})
                </button>
              ))}
              <button
                type="button"
                className="workspace-btn"
                disabled={busyCaseId === caseId}
                onClick={async () => {
                  setBusyCaseId(caseId)
                  try {
                    await onNewChatInCase(caseId, language)
                  } finally {
                    setBusyCaseId(null)
                  }
                }}
              >
                <MessageSquarePlus size={14} aria-hidden="true" />{' '}
                {busyCaseId === caseId ? 'Opening new chat…' : 'Start new chat in this case'}
              </button>
            </div>
          </section>
        )
      })}
    </div>
  )
}

export function VerifiedContactCards({
  conversationId,
  domain,
  onActionLogged,
}: {
  conversationId: string
  domain?: string
  onActionLogged?: () => void
}) {
  const [contacts, setContacts] = useState<VerifiedContact[]>([])
  const [asOf, setAsOf] = useState('')
  const [suppressedCount, setSuppressedCount] = useState(0)
  const [statusMsg, setStatusMsg] = useState('')

  useEffect(() => {
    let mounted = true
    api
      .verifiedContacts()
      .then(res => {
        if (!mounted) return
        setContacts(res.contacts || [])
        setAsOf(res.as_of || '')
        setSuppressedCount(res.suppressed_expired_count || 0)
      })
      .catch(() => {
        if (mounted) setContacts([])
      })
    return () => {
      mounted = false
    }
  }, [domain])

  async function recordUserReportedContact(contact: VerifiedContact) {
    try {
      await api.addUserAction(
        conversationId,
        `User-reported contact: ${contact.label} (${contact.destination})`,
        'completed',
        'User reported initiating contact; distinct from official filing confirmation.'
      )
      setStatusMsg(
        `Recorded user-reported contact with ${contact.label}. Note: opening a dialer or portal is not official filing confirmation.`
      )
      onActionLogged?.()
    } catch (e) {
      setStatusMsg((e as Error).message)
    }
  }

  return (
    <section className="verified-contacts-section" aria-label="Verified official contacts">
      <div className="workspace-inline-row">
        <b><PhoneCall size={15} aria-hidden="true" /> Verified Official Contact Registry</b>
        {asOf && <small className="muted">Verified as of {asOf}</small>}
      </div>
      <p className="muted">
        Destinations come strictly from the normalized official registry. Opening a dialer or portal does not establish
        official filing confirmation.
      </p>
      {suppressedCount > 0 && (
        <p className="workspace-warning">
          {suppressedCount} contact record(s) past their revalidation date are suppressed until refreshed from official
          sources.
        </p>
      )}
      <div className="workspace-stack">
        {contacts.map(c => (
          <div className="knowledge-card" key={c.id}>
            <div className="workspace-inline-row">
              <b>{c.label}</b>
              <small className="fact-badge">{c.channel_type.toUpperCase()} · {c.jurisdiction}</small>
            </div>
            <p style={{ margin: '0.25rem 0' }}>
              Destination: <b>{c.destination}</b>
            </p>
            <small className="muted">
              Checked: {c.checked_at} · Revalidate by: {c.revalidate_after}
            </small>
            <div className="step-buttons" style={{ marginTop: '0.4rem' }}>
              <a
                href={c.channel_type === 'phone' ? `tel:${c.destination}` : c.destination}
                target="_blank"
                rel="noreferrer"
                className="text-action"
              >
                {c.channel_type === 'phone' ? `Dial ${c.destination}` : 'Open official portal'} <ExternalLink size={12} />
              </a>
              <button type="button" onClick={() => void recordUserReportedContact(c)}>
                Record that I contacted this channel
              </button>
            </div>
          </div>
        ))}
      </div>
      {statusMsg && <small role="status" className="muted">{statusMsg}</small>}
    </section>
  )
}

export function DriveEvidenceSection({
  conversationId,
  onRefresh,
}: {
  conversationId: string
  onRefresh?: () => void
}) {
  const [connection, setConnection] = useState<GoogleProviderConnection | null>(null)
  const [folder, setFolder] = useState<DriveFolderInfo | null>(null)
  const [items, setItems] = useState<DriveManifestRecord[]>([])
  const [filename, setFilename] = useState('')
  const [fileText, setFileText] = useState('')
  const [statusMsg, setStatusMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function loadDrive() {
    try {
      const res = await api.driveManifest(conversationId)
      setConnection(res.connection)
      setFolder(res.folder)
      setItems(res.items || [])
    } catch {
      // Optional on legacy backend
    }
  }

  useEffect(() => {
    void loadDrive()
  }, [conversationId])

  async function connectDriveQuick() {
    setBusy(true)
    try {
      await api.connectGoogle({
        provider: 'google_drive',
        provider_account_email: 'citizen.user@gmail.com',
        granted_scopes: ['https://www.googleapis.com/auth/drive.file'],
        access_token: 'ya29.drive-scoped-token',
      })
      await loadDrive()
      setStatusMsg('Connected Google Drive with narrow drive.file scope.')
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function initFolder() {
    setBusy(true)
    try {
      const created = await api.createDriveFolder(conversationId)
      setFolder(created)
      setStatusMsg(`Opaque case folder ready: ${created.opaque_folder_name}`)
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function uploadOriginal() {
    if (!filename.trim()) return
    setBusy(true)
    try {
      const res = await api.uploadToDrive(conversationId, {
        filename: filename.trim(),
        text: fileText || `Original evidence record: ${filename.trim()}`,
        evidence_type: 'supporting_document',
        provenance: 'user_uploaded_original',
      })
      setFilename('')
      setFileText('')
      await loadDrive()
      setStatusMsg(
        res.duplicate_reused
          ? `Duplicate SHA-256 detected: reused existing manifest entry for ${res.item.filename}.`
          : `Saved original "${res.item.filename}" to Drive manifest (SHA-256: ${res.item.sha256.slice(0, 12)}…).`
      )
      onRefresh?.()
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function reconcileNow() {
    setBusy(true)
    try {
      const res = await api.reconcileDrive(conversationId, {})
      setItems(res.items || [])
      setStatusMsg(`Reconciled ${res.items?.length || 0} Drive manifest item(s).`)
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function cleanupTemp() {
    setBusy(true)
    try {
      const res = await api.cleanupTemporaryDriveData(conversationId)
      setStatusMsg(`Cleaned ${res.temporary_artifacts_cleaned} temporary processing text artifact(s).`)
      onRefresh?.()
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="drive-evidence-section workspace-stack" style={{ marginTop: '0.75rem' }}>
      <div className="workspace-inline-row">
        <b><FolderArchive size={15} aria-hidden="true" /> User-Owned Google Drive Case Folder & Manifest</b>
        <small className="fact-badge">
          {connection?.status === 'connected' ? `Connected (${connection.provider_account_email})` : 'Optional / Not connected'}
        </small>
      </div>
      <p className="muted">
        Uses narrow <code>drive.file</code> scope and opaque case folder names. Local V2 evidence is never migrated
        automatically.
      </p>

      {connection?.status !== 'connected' ? (
        <div className="step-buttons">
          <button type="button" disabled={busy} onClick={() => void connectDriveQuick()}>
            Connect Google Drive (drive.file)
          </button>
          <button type="button" disabled={busy} onClick={() => void cleanupTemp()}>
            <Trash2 size={13} /> Clean temporary processing text
          </button>
        </div>
      ) : (
        <>
          <div className="step-buttons">
            {!folder ? (
              <button type="button" disabled={busy} onClick={() => void initFolder()}>
                <FolderPlus size={14} /> Create Opaque Drive Case Folder
              </button>
            ) : (
              <span className="muted">
                Folder: <b>{folder.opaque_folder_name}</b> ({folder.sync_status})
              </span>
            )}
            <button type="button" disabled={busy} onClick={() => void reconcileNow()}>
              <RefreshCw size={13} /> Reconcile Drive status
            </button>
            <button type="button" disabled={busy} onClick={() => void cleanupTemp()}>
              <Trash2 size={13} /> Clean temporary text
            </button>
          </div>

          <div className="workspace-form-row">
            <input
              aria-label="Drive evidence filename"
              placeholder="Filename (e.g. bank-statement-utr.pdf)"
              value={filename}
              onChange={e => setFilename(e.target.value)}
            />
            <input
              aria-label="Drive evidence summary or content"
              placeholder="Content / excerpt to hash"
              value={fileText}
              onChange={e => setFileText(e.target.value)}
            />
            <button type="button" disabled={busy || !filename.trim()} onClick={() => void uploadOriginal()}>
              Add to Drive Manifest
            </button>
          </div>
        </>
      )}

      {items.length > 0 && (
        <div className="workspace-stack">
          {items.map(item => (
            <div className="knowledge-card" key={item.id}>
              <div className="workspace-inline-row">
                <b>{item.filename}</b>
                <small className="fact-badge">{item.sync_status} · SHA-256 {item.sha256.slice(0, 10)}…</small>
              </div>
              <small className="muted">{item.status_explanation}</small>
            </div>
          ))}
        </div>
      )}
      {statusMsg && <small role="status" className="muted">{statusMsg}</small>}
    </div>
  )
}

export function EmailReviewAndGmailSection({
  conversationId,
  attachments,
  drafts,
  onRefresh,
}: {
  conversationId: string
  attachments: Attachment[]
  drafts: Draft[]
  onRefresh?: () => void
}) {
  const [connection, setConnection] = useState<GoogleProviderConnection | null>(null)
  const [evidenceMessages, setEvidenceMessages] = useState<GmailEvidenceMessage[]>([])
  const [approvals, setApprovals] = useState<GmailApproval[]>([])
  const [dispatches, setDispatches] = useState<GmailDispatch[]>([])

  const [toInput, setToInput] = useState('grievance.officer@example.com')
  const [ccInput, setCcInput] = useState('')
  const [bccInput, setBccInput] = useState('')
  const [subject, setSubject] = useState(drafts[0]?.title || 'Formal Consumer Grievance & Refund Request')
  const [body, setBody] = useState(
    drafts[0]?.content || 'Please record this formal grievance and share the written complaint acknowledgment number.'
  )
  // Never attach all evidence by default! Start empty so user explicitly selects attachments.
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<string[]>([])
  const [activeApproval, setActiveApproval] = useState<GmailApproval | null>(null)
  const [approvedSnapshot, setApprovedSnapshot] = useState<string>('')
  const [statusMsg, setStatusMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const currentFormSnapshot = JSON.stringify({
    to: toInput.trim().toLowerCase(),
    cc: ccInput.trim().toLowerCase(),
    bcc: bccInput.trim().toLowerCase(),
    subject: subject.trim(),
    body,
    attachments: [...selectedAttachmentIds].sort(),
  })

  const isApprovalInvalidatedByEdit =
    Boolean(activeApproval) && approvedSnapshot !== '' && approvedSnapshot !== currentFormSnapshot

  async function loadGmail() {
    try {
      const res = await api.gmailState(conversationId)
      setConnection(res.connection)
      setEvidenceMessages(res.evidence_messages || [])
      setApprovals(res.approvals || [])
      setDispatches(res.dispatches || [])
    } catch {
      // Optional on legacy backend
    }
  }

  useEffect(() => {
    void loadGmail()
  }, [conversationId])

  async function connectGmailQuick() {
    setBusy(true)
    try {
      await api.connectGoogle({
        provider: 'google_gmail',
        provider_account_email: 'citizen.user@gmail.com',
        granted_scopes: [
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.send',
        ],
        access_token: 'ya29.gmail-scoped-token',
      })
      await loadGmail()
      setStatusMsg('Connected Gmail with separated readonly and reviewed-send permissions.')
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  function toggleAttachment(id: string) {
    setSelectedAttachmentIds(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]))
  }

  async function approveExactPayload() {
    setBusy(true)
    try {
      const created = await api.createGmailApproval(conversationId, {
        to_recipients: toInput.split(',').map(s => s.trim()).filter(Boolean),
        cc_recipients: ccInput.split(',').map(s => s.trim()).filter(Boolean),
        bcc_recipients: bccInput.split(',').map(s => s.trim()).filter(Boolean),
        subject: subject.trim(),
        body,
        selected_attachment_ids: selectedAttachmentIds,
      })
      setActiveApproval(created)
      setApprovedSnapshot(currentFormSnapshot)
      await loadGmail()
      setStatusMsg(`Approval bound to immutable payload hash ${created.payload_hash.slice(0, 12)}…`)
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function dispatchApprovedEmail() {
    if (!activeApproval) return
    setBusy(true)
    try {
      const res = await api.sendApprovedGmail(conversationId, {
        approval_id: activeApproval.id,
        to_recipients: toInput.split(',').map(s => s.trim()).filter(Boolean),
        cc_recipients: ccInput.split(',').map(s => s.trim()).filter(Boolean),
        bcc_recipients: bccInput.split(',').map(s => s.trim()).filter(Boolean),
        subject: subject.trim(),
        body,
        selected_attachment_ids: selectedAttachmentIds,
      })
      setActiveApproval(null)
      setApprovedSnapshot('')
      await loadGmail()
      setStatusMsg(res.notice)
      onRefresh?.()
    } catch (e) {
      setStatusMsg((e as Error).message)
      await loadGmail()
    } finally {
      setBusy(false)
    }
  }

  async function reconcileAmbiguous(approvalId: string, foundInSent: boolean) {
    setBusy(true)
    try {
      const res = await api.reconcileGmailSend(conversationId, {
        approval_id: approvalId,
        provider_sent_found: foundInSent,
      })
      await loadGmail()
      setStatusMsg(`Reconciled dispatch: ${res.outcome.replaceAll('_', ' ')}`)
    } catch (e) {
      setStatusMsg((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="gmail-review-section workspace-stack" aria-label="Reviewed Gmail communications">
      <div className="workspace-inline-row">
        <b><Mail size={15} aria-hidden="true" /> Reviewed Email Preparation & Payload-Bound Approval</b>
        <small className="fact-badge">
          {connection?.status === 'connected' ? `Gmail: ${connection.provider_account_email}` : 'Not connected'}
        </small>
      </div>
      <p className="muted">
        Nyay Saathi never sends email automatically and never attaches all evidence by default. Editing any recipient,
        subject, body, or attachment invalidates prior approval.
      </p>

      {connection?.status !== 'connected' && (
        <button type="button" className="workspace-btn" disabled={busy} onClick={() => void connectGmailQuick()}>
          Connect Gmail for Reviewed Correspondence
        </button>
      )}

      <div className="knowledge-card workspace-stack">
        <b>Email Review Screen</b>
        <small className="muted">
          Sender: <b>{connection?.provider_account_email || 'Connect Gmail account to send'}</b>
        </small>
        <label>
          To (comma-separated)
          <input
            aria-label="Email To recipients"
            value={toInput}
            onChange={e => setToInput(e.target.value)}
          />
        </label>
        <div className="workspace-form-row">
          <input
            aria-label="Email Cc recipients"
            placeholder="Cc (optional)"
            value={ccInput}
            onChange={e => setCcInput(e.target.value)}
          />
          <input
            aria-label="Email Bcc recipients"
            placeholder="Bcc (optional)"
            value={bccInput}
            onChange={e => setBccInput(e.target.value)}
          />
        </div>
        <label>
          Subject
          <input
            aria-label="Email Subject"
            value={subject}
            onChange={e => setSubject(e.target.value)}
          />
        </label>
        <label>
          Full Email Body
          <textarea
            aria-label="Email Full Body"
            rows={4}
            value={body}
            onChange={e => setBody(e.target.value)}
          />
        </label>

        <div>
          <b>Select specific attachments to include ({selectedAttachmentIds.length} selected)</b>
          {attachments.length === 0 ? (
            <p className="muted">No case attachments uploaded yet.</p>
          ) : (
            <div className="workspace-stack">
              {attachments.map(att => (
                <label className="consent-check" key={att.id}>
                  <input
                    type="checkbox"
                    checked={selectedAttachmentIds.includes(att.id)}
                    onChange={() => toggleAttachment(att.id)}
                  />
                  <span>{att.filename} ({att.extraction_status})</span>
                </label>
              ))}
            </div>
          )}
        </div>

        {isApprovalInvalidatedByEdit && (
          <p className="workspace-warning" role="alert">
            <AlertTriangle size={14} /> Material edit detected after approval. Previous approval hash is invalidated;
            click &ldquo;Approve Exact Payload&rdquo; again before sending.
          </p>
        )}

        <div className="step-buttons">
          <button
            type="button"
            disabled={busy || !toInput.trim() || !subject.trim() || !body.trim()}
            onClick={() => void approveExactPayload()}
          >
            <ShieldCheck size={14} /> 1. Approve Exact Payload
          </button>
          <button
            type="button"
            disabled={busy || !activeApproval || isApprovalInvalidatedByEdit}
            onClick={() => void dispatchApprovedEmail()}
          >
            <Send size={14} /> 2. Send Approved Email
          </button>
        </div>

        {activeApproval && !isApprovalInvalidatedByEdit && (
          <small className="muted">
            Approved payload hash: <code>{activeApproval.payload_hash.slice(0, 16)}…</code> · Expires:{' '}
            {activeApproval.expires_at}
          </small>
        )}
      </div>

      {evidenceMessages.length > 0 && (
        <div className="workspace-stack">
          <b>Imported Gmail Correspondence ({evidenceMessages.length})</b>
          {evidenceMessages.map(msg => (
            <div className="knowledge-card" key={msg.id}>
              <div className="workspace-inline-row">
                <b>{msg.subject}</b>
                <small className="muted">From: {msg.sender}</small>
              </div>
              <p className="muted">{msg.snippet || msg.body_text.slice(0, 200)}</p>
              {msg.untrusted_instruction_flags?.length > 0 && (
                <small className="workspace-warning">
                  Untrusted email instruction isolated ({msg.untrusted_instruction_flags.join(', ')}) — cannot modify
                  recipients or permissions.
                </small>
              )}
            </div>
          ))}
        </div>
      )}

      {dispatches.length > 0 && (
        <div className="workspace-stack">
          <b>Email Dispatch & Reconciliation Records ({dispatches.length})</b>
          {dispatches.map(d => (
            <div className="knowledge-card" key={d.id}>
              <div className="workspace-inline-row">
                <b>Status: {d.dispatch_status.replaceAll('_', ' ')}</b>
                <small className="fact-badge">Sent email ≠ official portal filing</small>
              </div>
              <small className="muted">{d.reconciliation_notes}</small>
              {d.dispatch_status === 'ambiguous_timeout_needs_reconciliation' && (
                <div className="step-buttons" style={{ marginTop: '0.4rem' }}>
                  <button type="button" onClick={() => void reconcileAmbiguous(d.approval_id, true)}>
                    Confirm found in Gmail Sent (do not resend)
                  </button>
                  <button type="button" onClick={() => void reconcileAmbiguous(d.approval_id, false)}>
                    Confirm not sent (allow retry)
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {statusMsg && <small role="status" className="muted">{statusMsg}</small>}
    </section>
  )
}

export function DistinctLifecycleTracker({
  conversationId,
  onRefresh,
}: {
  conversationId: string
  onRefresh?: () => void
}) {
  const [note, setNote] = useState('')
  const [statusMsg, setStatusMsg] = useState('')

  async function recordLifecycleKind(
    kind: 'submission' | 'promise' | 'processed_refund' | 'remedy_receipt' | 'closure',
    closureStatus?: string
  ) {
    try {
      await api.updateLifecycle(conversationId, {
        event_kind: kind,
        entry: { note: note.trim() || kind },
        closure_status: closureStatus,
      })
      setNote('')
      setStatusMsg(
        kind === 'promise'
          ? 'Recorded seller/company promise (case remains open until remedy receipt is confirmed).'
          : kind === 'processed_refund'
            ? 'Recorded merchant "refund processed" claim (distinct from actual credit receipt in your bank).'
            : kind === 'remedy_receipt'
              ? 'Recorded confirmed remedy receipt in your account.'
              : `Recorded ${kind.replaceAll('_', ' ')}.`
      )
      onRefresh?.()
    } catch (e) {
      setStatusMsg((e as Error).message)
    }
  }

  return (
    <div className="knowledge-card workspace-stack" style={{ marginTop: '0.6rem' }}>
      <b><CheckCircle2 size={14} aria-hidden="true" /> Distinct Outcome & Remedy Lifecycle</b>
      <p className="muted">
        A seller promise or &ldquo;refund processed&rdquo; SMS is not proof that money reached your bank. Keep each stage
        separate:
      </p>
      <input
        aria-label="Lifecycle event reference or note"
        placeholder="Reference / UTR / promised date (optional)"
        value={note}
        onChange={e => setNote(e.target.value)}
      />
      <div className="step-buttons">
        <button type="button" onClick={() => void recordLifecycleKind('promise')}>
          Log Promise Made
        </button>
        <button type="button" onClick={() => void recordLifecycleKind('processed_refund')}>
          Log &ldquo;Refund Processed&rdquo; Claim
        </button>
        <button type="button" onClick={() => void recordLifecycleKind('remedy_receipt')}>
          Confirm Remedy Received
        </button>
        <button type="button" onClick={() => void recordLifecycleKind('closure', 'resolved_confirmed')}>
          Mark Case Closed
        </button>
      </div>
      {statusMsg && <small role="status" className="muted">{statusMsg}</small>}
    </div>
  )
}
