import { Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type UserKeyStatus } from '../api'

/** Each user's own OpenAI key: checked with OpenAI, stored so that only this browser can unlock it. */
export default function UserKeyCard({ onChange }: { onChange?: (configured: boolean) => void }) {
  const [status, setStatus] = useState<UserKeyStatus | null>(null)
  const [key, setKey] = useState(''), [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  useEffect(() => { api.userKey().then(setStatus).catch(e => setMessage({ kind: 'error', text: (e as Error).message })) }, [])

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
  </div>
}
