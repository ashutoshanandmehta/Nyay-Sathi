// Live voice input: browser → OpenAI Realtime over WebRTC with a short-lived secret from
// our backend (the API key never reaches the browser). A local MediaRecorder runs alongside
// so the existing /api/audio/transcribe can still produce text if the live path fails.
import { api } from './api'

export type VoiceState = 'connecting' | 'listening' | 'finishing'
interface LiveSecret { client_secret: string; expires_at: number; model: string; max_seconds: number }
export interface LiveHandlers {
  onText: (final: string, partial: string) => void
  onState?: (state: VoiceState) => void
  onLevel?: (level: number) => void
  onLimit?: () => void
}
export interface LiveRecording { stop: () => Promise<string>; cancel: () => void }

const CALLS_URL = 'https://api.openai.com/v1/realtime/calls'
const FINISH_WAIT_MS = 2000
let secret: Promise<LiveSecret | null> | null = null
let secretUntil = 0

/** Mint (or reuse) the live secret ahead of time, so pressing Mic only pays for the handshake. */
export function prewarm(): Promise<LiveSecret | null> {
  const now = Date.now() / 1000
  if (secret && now < secretUntil - 15) return secret
  secretUntil = now + 60
  secret = fetch('/api/audio/live-session', { credentials: 'include' })
    .then(async r => {
      if (!r.ok) return null
      const value = (await r.json()) as LiveSecret
      secretUntil = value.expires_at
      return value
    })
    .catch(() => null)
  return secret
}

/** Test hook: forget the cached secret. */
export function resetVoiceCache() { secret = null; secretUntil = 0 }

export async function startLiveTranscription(handlers: LiveHandlers): Promise<LiveRecording> {
  handlers.onState?.('connecting')
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  const tracks = stream.getAudioTracks()

  // Fallback copy of the audio; local only, costs nothing unless it has to be uploaded.
  const chunks: Blob[] = []
  const recorder = typeof MediaRecorder !== 'undefined' ? new MediaRecorder(stream) : null
  if (recorder) { recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }; recorder.start(250) }

  // Level meter for the button ring.
  let audio: AudioContext | null = null, raf = 0
  try {
    audio = new AudioContext()
    const analyser = audio.createAnalyser()
    analyser.fftSize = 512
    audio.createMediaStreamSource(stream).connect(analyser)
    const data = new Uint8Array(analyser.fftSize)
    const tick = () => {
      analyser.getByteTimeDomainData(data)
      let sum = 0
      for (const v of data) sum += ((v - 128) / 128) ** 2
      handlers.onLevel?.(Math.min(1, Math.sqrt(sum / data.length) * 4))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
  } catch { audio = null }

  // Transcript state, ordered by when each spoken segment first appears.
  const order: string[] = [], finals = new Map<string, string>(), partials = new Map<string, string>()
  let frame = 0, scheduled = false
  const join = (m: Map<string, string>) => order.map(id => m.get(id)).filter(Boolean).join(' ').trim()
  // At most one UI update per animation frame, however fast the deltas arrive.
  const emit = () => {
    if (scheduled) return
    scheduled = true
    frame = requestAnimationFrame(() => { scheduled = false; frame = 0; handlers.onText(join(finals), join(partials)) })
  }
  const seen = (id: string) => { if (!order.includes(id)) order.push(id) }
  let committed = false, waiting: (() => void) | null = null
  const settled = () => committed && partials.size === 0

  let pc: RTCPeerConnection | null = null, channel: RTCDataChannel | null = null, live = false
  try {
    const session = await prewarm()
    if (!session) throw new Error('no live session')
    pc = new RTCPeerConnection()
    for (const track of tracks) pc.addTrack(track, stream)
    channel = pc.createDataChannel('oai-events')
    channel.onmessage = event => {
      let message: { type?: string; item_id?: string; delta?: string; transcript?: string }
      try { message = JSON.parse(event.data) } catch { return }
      const id = message.item_id || ''
      if (message.type === 'conversation.item.input_audio_transcription.delta' && id) {
        seen(id); partials.set(id, (partials.get(id) || '') + (message.delta || '')); emit()
      } else if (message.type === 'conversation.item.input_audio_transcription.completed' && id) {
        seen(id); partials.delete(id); finals.set(id, (message.transcript || '').trim()); emit()
      } else if (message.type === 'conversation.item.input_audio_transcription.failed' && id) {
        partials.delete(id)
      } else if (message.type === 'input_audio_buffer.committed' && id) {
        seen(id); if (!finals.has(id)) partials.set(id, partials.get(id) || '')
      }
      if (message.type === 'input_audio_buffer.committed' || message.type === 'error') committed = true
      if (waiting && settled()) waiting()
    }
    const opened = new Promise<void>(resolve => { channel!.onopen = () => resolve() })
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const answer = await fetch(CALLS_URL, {
      method: 'POST',
      body: offer.sdp,
      headers: { Authorization: `Bearer ${session.client_secret}`, 'Content-Type': 'application/sdp' },
    })
    if (!answer.ok) throw new Error('live call refused')
    await pc.setRemoteDescription({ type: 'answer', sdp: await answer.text() })
    await opened
    live = true
    const limit = setTimeout(() => handlers.onLimit?.(), session.max_seconds * 1000)
    pc.addEventListener('connectionstatechange', () => { if (pc?.connectionState === 'closed') clearTimeout(limit) })
  } catch {
    pc?.close(); pc = null; channel = null; live = false
  }
  handlers.onState?.('listening')

  let done = false
  const cleanup = () => {
    done = true
    cancelAnimationFrame(raf); if (frame) cancelAnimationFrame(frame)
    tracks.forEach(t => t.stop())
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    pc?.close()
    void audio?.close().catch(() => undefined)
  }
  const recorded = () => new Promise<Blob | null>(resolve => {
    if (!recorder) return resolve(null)
    const finish = () => resolve(chunks.length ? new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }) : null)
    if (recorder.state === 'inactive') return finish()
    recorder.onstop = finish
    recorder.stop()
  })

  return {
    async stop() {
      if (done) return ''
      handlers.onState?.('finishing')
      // Stop sending audio at once; keep the channel open for the last segment's text.
      tracks.forEach(t => t.stop())
      const clip = await recorded()
      if (live && channel?.readyState === 'open') {
        // Wait for this commit, not an earlier pause's, before reading the text.
        committed = false
        channel.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))
        await new Promise<void>(resolve => {
          if (settled()) return resolve()
          const timer = setTimeout(resolve, FINISH_WAIT_MS)
          waiting = () => { clearTimeout(timer); resolve() }
        })
      }
      // Anything still mid-segment is kept rather than lost.
      const text = [join(finals), join(partials)].filter(Boolean).join(' ').trim()
      cleanup()
      if (text || !clip) return text
      const result = await api.transcribe(new File([clip], 'recording.webm', { type: clip.type }))
      return result.transcript.trim()
    },
    cancel() { if (!done) cleanup() },
  }
}
