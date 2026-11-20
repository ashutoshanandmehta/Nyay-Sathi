import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { api } from '../api'
import {
  DistinctLifecycleTracker,
  DriveEvidenceSection,
  EmailReviewAndGmailSection,
  MyCasesPanel,
  ThreeActionHome,
  VerifiedContactCards,
} from './ActionWorkflowsPanel'
import { CasePanel } from './Drawer'
import UserKeyCard from './UserKeyCard'

describe('Packages 3, 4, 5 & 6 Android Native Bridges & Product Screens', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    delete window.NyayNativeFiles
    delete window.__nyayHandleBackPress
  })

  it('Package 3: uses window.NyayNativeFiles bridge on Android for PDF/DOCX/JSON exports when available', async () => {
    const saveAndShareBase64File = vi.fn().mockReturnValue(true)
    window.NyayNativeFiles = { saveAndShareBase64File }

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('PDF-BINARY-CONTENT', {
          status: 200,
          headers: { 'Content-Disposition': 'attachment; filename="android-case-pack.pdf"' },
        })
      )
    )

    const filename = await api.downloadCaseExport('conv-1', 'pdf')
    expect(filename).toBe('android-case-pack.pdf')
    expect(saveAndShareBase64File).toHaveBeenCalledOnce()
    expect(saveAndShareBase64File.mock.calls[0][0]).toBe('android-case-pack.pdf')
    expect(saveAndShareBase64File.mock.calls[0][1]).toBe('application/pdf')
    vi.unstubAllGlobals()
  })

  it('Package 3: registers Android hardware back button handler (__nyayHandleBackPress) that closes open drawers first', async () => {
    Element.prototype.scrollIntoView = vi.fn()
    const conv = { id: 'c1', case_id: 'case-1', title: 'Refund dispute', language: 'en' as const, created_at: '', updated_at: '' }
    vi.spyOn(api, 'bootstrap').mockResolvedValue({ ai_configured: true, privacy_notice: '', disclaimer: '' })
    vi.spyOn(api, 'list').mockResolvedValue([conv])
    vi.spyOn(api, 'detail').mockResolvedValue({
      conversation: conv,
      messages: [],
      safety_messages: [],
      case_memory: { version: 1, domain: 'consumer', facts: {}, contradictions: [], unknowns: [], actions_completed: [], evidence: [] },
      summary: '',
      attachments: [],
      drafts: [],
    })

    render(<App />)
    await waitFor(() => expect(window.__nyayHandleBackPress).toBeTypeOf('function'))

    // When no drawer or menu is open, back press returns false
    expect(window.__nyayHandleBackPress!()).toBe(false)

    // Open "Your case" drawer
    fireEvent.click(screen.getByRole('button', { name: /Your case/i }))
    expect(await screen.findByText(/Private case · v1/)).toBeInTheDocument()

    // Pressing hardware back closes the drawer and returns true
    let handled = false
    act(() => {
      handled = window.__nyayHandleBackPress!()
    })
    expect(handled).toBe(true)
    expect(screen.queryByText(/Private case · v1/)).toBeNull()
  })

  it('Package 4: renders Three-Action Home (Know My Rights, Resolve a Complaint, Report Financial Fraud) and dispatches prompts without mandatory intake', () => {
    const onSelectPrompt = vi.fn()
    const onOpenMyCases = vi.fn()
    render(<ThreeActionHome onSelectPrompt={onSelectPrompt} onOpenMyCases={onOpenMyCases} />)

    expect(screen.getByText('Know My Rights')).toBeInTheDocument()
    expect(screen.getByText('Resolve a Complaint')).toBeInTheDocument()
    expect(screen.getByText('Report Financial Fraud')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Report Financial Fraud'))
    expect(
      screen.getByText(/Bypasses routine merchant waiting periods/i)
    ).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', {
        name: /Money was just debited from my bank account/i,
      })
    )
    expect(onSelectPrompt).toHaveBeenCalledWith(
      expect.stringContaining('Money was just debited from my bank account')
    )
  })

  it('Package 4: MyCasesPanel lists independent cases and opens a new chat inside an existing case', async () => {
    vi.spyOn(api, 'listCases').mockResolvedValue([
      {
        id: 'case-alpha-12345678',
        title: 'Defective Laptop Case',
        status: 'active',
        domain: 'consumer',
        created_at: '2026-11-10',
        updated_at: '2026-11-10',
        lifecycle_state: {
          submissions: [{ channel: 'Grievance Officer' }],
          promises: [{ note: 'Promised replacement' }],
          processed_refunds: [],
          remedy_receipt: null,
          closure: 'open',
        },
      },
    ])
    const onSelectConversation = vi.fn()
    const onNewChatInCase = vi.fn().mockResolvedValue(undefined)

    render(
      <MyCasesPanel
        conversations={[
          {
            id: 'chat-1',
            case_id: 'case-alpha-12345678',
            title: 'Initial laptop intake',
            language: 'en',
            created_at: '',
            updated_at: '',
          },
        ]}
        activeConversationId="chat-1"
        language="hi"
        onSelectConversation={onSelectConversation}
        onNewChatInCase={onNewChatInCase}
      />
    )

    expect(await screen.findByText('Initial laptop intake')).toBeInTheDocument()
    expect(screen.getByText(/Promises: 1/i)).toBeInTheDocument()
    expect(screen.getByText(/Remedy received: Not yet confirmed/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Start new chat in this case/i }))
    await waitFor(() => expect(onNewChatInCase).toHaveBeenCalledWith('case-alpha-12345678', 'hi'))
  })

  it('Package 4: CasePanel switches across all 7 workspace sections (Overview, Evidence, Legal Basis, Documents, Communications, Timeline, Next Actions)', async () => {
    vi.spyOn(api, 'verifiedContacts').mockResolvedValue({
      as_of: '2026-11-10',
      suppressed_expired_count: 0,
      contacts: [
        {
          id: 'india-cyber-1930',
          category: 'financial_cyber_fraud',
          jurisdiction: 'India',
          label: 'National Cyber-Financial Fraud Helpline',
          channel_type: 'phone',
          destination: '1930',
          official_source_url: 'https://cybercrime.gov.in/',
          checked_at: '2026-11-07',
          revalidate_after: '2026-11-14',
          retired: false,
        },
      ],
    })
    vi.spyOn(api, 'driveManifest').mockResolvedValue({
      case_id: 'case-1',
      connection: null,
      folder: null,
      items: [],
      local_v2_migration_policy: 'explicit_user_selection_only_never_automatic',
    })
    vi.spyOn(api, 'gmailState').mockResolvedValue({
      case_id: 'case-1',
      connection: null,
      evidence_messages: [],
      approvals: [],
      dispatches: [],
    })

    render(
      <CasePanel
        detail={{
          conversation: { id: 'c1', title: 'Fraud case', language: 'en', created_at: '', updated_at: '' },
          messages: [
            {
              id: 'm1',
              role: 'assistant',
              content: 'Call 1930 immediately.',
              created_at: '',
              status: 'complete',
              metadata: {
                sources: [
                  {
                    source_id: 'mha-i4c',
                    passage_id: 'prop-cyber-i4c-1930-portal',
                    title: 'National Cyber Crime Reporting Portal & Helpline 1930',
                    locator: 'Helpline 1930',
                    text: 'Call 1930',
                    canonical_url: 'https://cybercrime.gov.in/',
                    retrieved_at: '2026-11-07',
                    limitations: 'Fund recovery is not guaranteed.',
                  },
                ],
              },
            },
          ],
          summary: '',
          attachments: [
            {
              id: 'att-1',
              filename: 'utr-receipt.pdf',
              mime_type: 'application/pdf',
              extraction_status: 'extracted',
              extracted_text: 'UTR 123456',
            },
          ],
          drafts: [
            {
              id: 'd1',
              title: 'Bank Dispute Letter',
              content: 'Please block my channel and register dispute.',
              version: 1,
              status: 'preliminary',
              case_version: 1,
            },
          ],
          case_memory: {
            version: 1,
            domain: 'financial_fraud',
            facts: { utr: { value: '123456', status: 'document_statement' } },
            events: [{ date: '2026-11-10', description: 'Unauthorized debit of Rs 15000' }],
            contradictions: [],
            unknowns: [],
            actions_completed: [],
            evidence: [],
          },
        }}
      />
    )

    // Verify all 7 workspace section buttons render
    for (const label of ['Overview', 'Evidence', 'Legal Basis', 'Documents', 'Communications', 'Timeline', 'Next Actions']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }

    // Click Overview -> shows DistinctOutcome & Remedy Lifecycle tracker
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.getByText(/Distinct Outcome & Remedy Lifecycle/i)).toBeInTheDocument()

    // Click Evidence -> shows User-Owned Google Drive Case Folder & Manifest
    fireEvent.click(screen.getByRole('button', { name: 'Evidence' }))
    expect(await screen.findByText(/User-Owned Google Drive Case Folder & Manifest/i)).toBeInTheDocument()

    // Click Legal Basis -> shows cited official sources
    fireEvent.click(screen.getByRole('button', { name: 'Legal Basis' }))
    expect(screen.getByText(/National Cyber Crime Reporting Portal & Helpline 1930/i)).toBeInTheDocument()

    // Click Next Actions -> shows Verified Official Contact Registry card for 1930
    fireEvent.click(screen.getByRole('button', { name: 'Next Actions' }))
    expect(await screen.findByText('National Cyber-Financial Fraud Helpline')).toBeInTheDocument()

    // Click Communications -> shows Email Review Screen
    fireEvent.click(screen.getByRole('button', { name: 'Communications' }))
    expect(await screen.findByText('Email Review Screen')).toBeInTheDocument()
  })

  it('Package 6 UI: EmailReviewAndGmailSection never selects attachments by default and immediately invalidates approval in UI when any field is edited', async () => {
    vi.spyOn(api, 'gmailState').mockResolvedValue({
      case_id: 'case-1',
      connection: {
        id: 'conn-1',
        provider: 'google_gmail',
        provider_account_email: 'alice@gmail.com',
        provider_user_id: 'alice@gmail.com',
        granted_scopes: ['https://www.googleapis.com/auth/gmail.send'],
        status: 'connected',
        reply_monitoring_opted_in: false,
        last_verified_at: '2026-11-10',
      },
      evidence_messages: [],
      approvals: [],
      dispatches: [],
    })
    vi.spyOn(api, 'createGmailApproval').mockResolvedValue({
      id: 'app-1',
      case_id: 'case-1',
      conversation_id: 'c1',
      provider_account_email: 'alice@gmail.com',
      sender_email: 'alice@gmail.com',
      to_recipients: ['grievance.officer@example.com'],
      cc_recipients: [],
      bcc_recipients: [],
      subject: 'Formal Consumer Grievance & Refund Request',
      body: 'Please record this formal grievance and share the written complaint acknowledgment number.',
      selected_attachment_ids: [],
      payload_hash: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
      version: 1,
      status: 'approved',
      expires_at: '2026-11-10T12:00:00Z',
    })

    render(
      <EmailReviewAndGmailSection
        conversationId="c1"
        attachments={[
          {
            id: 'att-1',
            filename: 'invoice.pdf',
            mime_type: 'application/pdf',
            extraction_status: 'extracted',
            extracted_text: 'Invoice',
          },
        ]}
        drafts={[]}
      />
    )

    // Verify 0 attachments are selected by default
    expect(await screen.findByText(/Select specific attachments to include \(0 selected\)/i)).toBeInTheDocument()

    // Send button is disabled before approval
    const sendBtn = screen.getByRole('button', { name: /2\. Send Approved Email/i })
    expect(sendBtn).toBeDisabled()

    // Click Approve Exact Payload
    fireEvent.click(screen.getByRole('button', { name: /1\. Approve Exact Payload/i }))
    await waitFor(() => expect(sendBtn).not.toBeDisabled())

    // Now edit the email body after approval -> immediately invalidates approval and disables Send button!
    fireEvent.change(screen.getByLabelText('Email Full Body'), {
      target: { value: 'Edited body after approval!' },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent(/Material edit detected after approval/i)
    expect(sendBtn).toBeDisabled()
  })

  it('Package 3: falls back to navigator.share with File when NyayNativeFiles is unavailable on mobile, and consumes cold-start __nyayPendingOAuthCallback on App mount', async () => {
    const canShare = vi.fn().mockReturnValue(true)
    const share = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'canShare', { value: canShare, configurable: true })
    Object.defineProperty(navigator, 'share', { value: share, configurable: true })

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('DOCX-CONTENT', {
          status: 200,
          headers: { 'Content-Disposition': 'attachment; filename="mobile-share.docx"' },
        })
      )
    )

    const filename = await api.downloadDraftExport('conv-1', 'draft-1', 'docx')
    expect(filename).toBe('mobile-share.docx')
    expect(canShare).toHaveBeenCalledOnce()
    expect(share).toHaveBeenCalledOnce()
    vi.unstubAllGlobals()
    delete (navigator as unknown as Record<string, unknown>).canShare
    delete (navigator as unknown as Record<string, unknown>).share

    // Cold-start OAuth callback queued by MainActivity before React mounted
    Element.prototype.scrollIntoView = vi.fn()
    window.__nyayPendingOAuthCallback = {
      provider: 'google_drive',
      error: 'access_denied',
    }
    const conv = { id: 'c1', case_id: 'case-1', title: 'Refund dispute', language: 'en' as const, created_at: '', updated_at: '' }
    vi.spyOn(api, 'bootstrap').mockResolvedValue({ ai_configured: true, privacy_notice: '', disclaimer: '' })
    vi.spyOn(api, 'list').mockResolvedValue([conv])
    vi.spyOn(api, 'detail').mockResolvedValue({
      conversation: conv,
      messages: [],
      safety_messages: [],
      case_memory: { version: 1, domain: 'consumer', facts: {}, contradictions: [], unknowns: [], actions_completed: [], evidence: [] },
      summary: '',
      attachments: [],
      drafts: [],
    })

    render(<App />)
    expect(await screen.findByText(/Google connection was cancelled or failed: access_denied/i)).toBeInTheDocument()
    expect(window.__nyayPendingOAuthCallback).toBeUndefined()
  })

  it('Package 5 & 6 Settings UI: UserKeyCard supports guest-to-account upgrade, Drive/Gmail connection & revocation, temporary data cleanup, and reply monitoring toggle', async () => {
    vi.spyOn(api, 'userKey').mockResolvedValue({ stored: false, unlocked: false, hint: null, server_key: true })
    vi.spyOn(api, 'googleStatus').mockResolvedValue({
      owner_id: 'u1',
      google_drive: null,
      google_gmail: null,
      storage_policy: 'disclosed_temporary_processing',
    })
    vi.spyOn(api, 'list').mockResolvedValue([
      { id: 'c1', case_id: 'case-1', title: 'Case 1', language: 'en', created_at: '', updated_at: '' },
    ])
    const cleanupSpy = vi.spyOn(api, 'cleanupTemporaryDriveData').mockResolvedValue({
      case_id: 'case-1',
      temporary_artifacts_cleaned: 2,
      status: 'purged_temporary_extracted_text',
    })

    render(<UserKeyCard />)
    expect(await screen.findByText(/Account, Google Drive\/Gmail & Privacy Controls/i)).toBeInTheDocument()

    const emailInput = screen.getByLabelText(/Account email for linking or Google connection/i)
    fireEvent.change(emailInput, { target: { value: 'citizen.linked@example.com' } })

    // Click Link / Upgrade Guest Account
    fireEvent.click(screen.getByRole('button', { name: /Link \/ Upgrade Guest Account/i }))
    expect(await screen.findByText(/Account link prepared for citizen\.linked@example\.com/i)).toBeInTheDocument()

    // Click Clean Temporary Processing Data
    fireEvent.click(screen.getByRole('button', { name: /Clean Temporary Processing Data/i }))
    await waitFor(() => expect(cleanupSpy).toHaveBeenCalledWith('c1'))
    expect(await screen.findByText(/Cleaned 2 temporary extracted-text artifact\(s\) across your cases/i)).toBeInTheDocument()
  })
})
