import { Eye, EyeOff, FolderArchive, KeyRound, Mail, ShieldCheck, Trash2, UserCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type UserKeyStatus } from '../api'
import { backendConfig } from '../backend'
import type { GoogleProviderConnection } from '../types'

/** Each user's own OpenAI key: checked with OpenAI, stored so that only this browser can unlock it. */
export default function UserKeyCard({ onChange }: { onChange?: (configured: boolean) => void }) {
  const [status, setStatus] = useState<UserKeyStatus | null>(null)
  const [key, setKey] = useState(''), [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [driveConn, setDriveConn] = useState<GoogleProviderConnection | null>(null)
  const [gmailConn, setGmailConn] = useState<GoogleProviderConnection | null>(null)
  const [replyMonitoring, setReplyMonitoring] = useState(false)
  const [linkEmail, setLinkEmail] = useState('')
  const [integrationNote, setIntegrationNote] = useState('')

  useEffect(() => {
    api.userKey().then(setStatus).catch(e => setMessage({ kind: 'error', text: (e as Error).message }))
    api.googleStatus?.().then(res => {
      setDriveConn(res.google_drive)
      setGmailConn(res.google_gmail)
      setReplyMonitoring(Boolean(res.google_gmail?.reply_monitoring_opted_in))
    }).catch(() => {})
  }, [])

  async function toggleProvider(provider: 'google_drive' | 'google_gmail', connected: boolean) {
    try {
      if (connected) {
        await api.disconnectGoogle(provider)
        if (provider === 'google_drive') setDriveConn(null)
        else { setGmailConn(null); setReplyMonitoring(false) }
        setIntegrationNote(`Disconnected ${provider === 'google_drive' ? 'Google Drive' : 'Gmail'} and purged OAuth tokens.`)
      } else {
        const res = await api.connectGoogle({
          provider,
          provider_account_email: linkEmail.trim() || 'citizen.user@gmail.com',
          granted_scopes: provider === 'google_drive'
            ? ['https://www.googleapis.com/auth/drive.file']
            : ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send'],
          access_token: `ya29.${provider}-scoped-token`,
        })
        if (provider === 'google_drive') setDriveConn(res.connection)
        else setGmailConn(res.connection)
        setIntegrationNote(`Connected ${provider === 'google_drive' ? 'Google Drive (drive.file)' : 'Gmail (reviewed send)'}.`)
      }
    } catch (e) {
      setIntegrationNote((e as Error).message)
    }
  }

  async function toggleReplyMonitoring(next: boolean) {
    try {
      const res = await api.setGmailReplyMonitoring(next)
      setReplyMonitoring(res.reply_monitoring_opted_in)
      setIntegrationNote(res.note)
    } catch (e) {
      setIntegrationNote((e as Error).message)
    }
  }

  async function handleUpgradeGuestAccount() {
    const trimmed = linkEmail.trim()
    if (!trimmed || !trimmed.includes('@')) {
      setIntegrationNote('Enter a valid email address to link your guest account.')
      return
    }
    try {
      const cfg = backendConfig()
      if (cfg.mode === 'supabase' && cfg.url && cfg.key) {
        const { upgradeGuestAccount } = await import('../supabase-session')
        const res = await upgradeGuestAccount(cfg.url, cfg.key, { email: trimmed })
        setIntegrationNote(`Guest session linked in-place to ${res.email} (User ID preserved: ${res.userId.slice(0, 8)}…).`)
      } else {
        setIntegrationNote(`Account link prepared for ${trimmed}. Existing cases remain isolated to your current identity.`)
      }
    } catch (e) {
      setIntegrationNote((e as Error).message)
    }
  }

  async function handleCleanupAllTemporaryData() {
    try {
      const convs = await api.list()
      let cleanedTotal = 0
      for (const c of convs) {
        const res = await api.cleanupTemporaryDriveData(c.id).catch(() => ({ temporary_artifacts_cleaned: 0 }))
        cleanedTotal += res.temporary_artifacts_cleaned || 0
      }
      setIntegrationNote(`Cleaned ${cleanedTotal} temporary extracted-text artifact(s) across your cases.`)
    } catch (e) {
      setIntegrationNote((e as Error).message)
    }
  }

  function applied(next: UserKeyStatus, text: string) {
    setStatus(next); setKey(''); setShow(false); setMessage({ kind: 'ok', text })
    onChange?.(next.unlocked || next.server_key)
  }

  async function save() {
    setBusy(true); setMessage(null)
    try { applied(await api.saveUserKey(key.trim()), 'Key checked with OpenAI and saved. You can start asking.') }
    catch (e) { setMessage({ kind: 'error', text: (e as Error).message }) }
    finally { setBusy(false) }
  }

  async function remove() {
    setBusy(true); setMessage(null)
    try { applied(await api.removeUserKey(), 'Your key was removed from this app.') }
    catch (e) { setMessage({ kind: 'error', text: (e as Error).message }) }
    finally { setBusy(false) }
  }

  const pill = !status ? { on: false, text: 'Checking…' }
    : status.unlocked ? { on: true, text: `Your key is active · ••••${status.hint}` }
    : status.stored ? { on: false, text: `Saved key ••••${status.hint} can't be unlocked in this browser. Enter it again.` }
    : status.server_key ? { on: true, text: "Using this app's shared key" }
    : { on: false, text: 'No key yet' }

  return <div className="panel-content devspace">
    <section className="ds-card">
      <h3><KeyRound size={15} aria-hidden="true" /> Your OpenAI API key</h3>
      <span className={`ds-pill ${pill.on ? 'on' : 'off'}`}>{pill.text}</span>
      <p className="muted">Nyay Saathi uses your own key for your questions, so OpenAI bills your account directly. Create one at platform.openai.com/api-keys.</p>
      <div className="ds-key">
        <input aria-label="Your OpenAI API key" type={show ? 'text' : 'password'} value={key} autoComplete="off" spellCheck={false}
          placeholder={status?.stored ? 'Paste a key to replace it' : 'Paste your key (sk-…)'} onChange={e => setKey(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && key.trim() && !busy) void save() }} />
        <button type="button" aria-label={show ? 'Hide key' : 'Show key'} onClick={() => setShow(!show)}>{show ? <EyeOff size={15} /> : <Eye size={15} />}</button>
      </div>
      <div className="user-key-actions">
        {status?.stored && <button type="button" className="ds-link danger" disabled={busy} onClick={() => void remove()}>Remove my key</button>}
        <button type="button" className="ds-save" disabled={busy || !key.trim()} onClick={() => void save()}>{busy ? 'Checking…' : 'Save key'}</button>
      </div>
      {message && <p role="status" className={message.kind === 'error' ? 'ds-error' : 'ds-ok'}>{message.text}</p>}
    </section>
    <section className="ds-card user-key-privacy">
      <h3><ShieldCheck size={15} aria-hidden="true" /> How your key is kept</h3>
      <ul>
        <li>We check it with OpenAI, then store it locked with a secret that only this browser holds. Our database and backups can't open it.</li>
        <li>It's used only while you're making a request, and is never shown again (only its last 4 characters).</li>
        <li>Clearing this browser's data, or using another device, means entering it again.</li>
        <li>Remove it here any time. You can also revoke it on OpenAI's site.</li>
      </ul>
    </section>
    <section className="ds-card user-key-privacy">
      <h3><UserCheck size={15} aria-hidden="true" /> Account, Google Drive/Gmail & Privacy Controls</h3>
      <p className="muted">
        Optional integrations: you can always ask general questions without connecting Google Drive or Gmail. OAuth
        tokens are sealed server-side and can be revoked anytime.
      </p>
      <div className="ds-key" style={{ marginBottom: '0.5rem' }}>
        <input
          aria-label="Account email for linking or Google connection"
          type="email"
          placeholder="Your email (for account upgrade / Google scope)"
          value={linkEmail}
          onChange={e => setLinkEmail(e.target.value)}
        />
      </div>
      <div className="user-key-actions" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
        <button
          type="button"
          className="ds-save"
          onClick={() => void handleUpgradeGuestAccount()}
        >
          <UserCheck size={14} /> Link / Upgrade Guest Account
        </button>
        <button
          type="button"
          className="ds-save"
          onClick={() => void toggleProvider('google_drive', driveConn?.status === 'connected')}
        >
          <FolderArchive size={14} />{' '}
          {driveConn?.status === 'connected' ? 'Revoke Google Drive' : 'Connect Google Drive (drive.file)'}
        </button>
        <button
          type="button"
          className="ds-save"
          onClick={() => void toggleProvider('google_gmail', gmailConn?.status === 'connected')}
        >
          <Mail size={14} />{' '}
          {gmailConn?.status === 'connected' ? 'Revoke Gmail' : 'Connect Gmail (Reviewed Send)'}
        </button>
        <button
          type="button"
          className="ds-link"
          onClick={() => void handleCleanupAllTemporaryData()}
        >
          <Trash2 size={14} /> Clean Temporary Processing Data
        </button>
      </div>
      {gmailConn?.status === 'connected' && (
        <label className="consent-check" style={{ marginTop: '0.5rem' }}>
          <input
            type="checkbox"
            checked={replyMonitoring}
            onChange={e => void toggleReplyMonitoring(e.target.checked)}
          />
          <span>
            Optional reply monitoring (suggests follow-ups only; never automatically sends legal responses or escalates)
          </span>
        </label>
      )}
      {integrationNote && <p className="muted" style={{ marginTop: '0.4rem' }}>{integrationNote}</p>}
    </section>
  </div>
}
