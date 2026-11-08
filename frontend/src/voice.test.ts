import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import { prewarm, resetVoiceCache, startLiveTranscription } from './voice'

const SECRET = { client_secret: 'ek_test', expires_at: Date.now() / 1000 + 120, model: 'gpt-realtime-whisper', max_seconds: 180 }

class FakeChannel {
  readyState = 'open'
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  send(data: string) {
    this.sent.push(data)
    // The service commits the last audio and finishes its transcript.
    queueMicrotask(() => {
      this.emit({ type: 'input_audio_buffer.committed', item_id: 'i2' })
      this.emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'i2', transcript: 'near Patna.' })
    })
  }
  emit(message: object) { this.onmessage?.({ data: JSON.stringify(message) }) }
}

let channel: FakeChannel, pcClosed: boolean, tracks: { stop: ReturnType<typeof vi.fn> }[], fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  resetVoiceCache()
  channel = new FakeChannel(); pcClosed = false
  tracks = [{ stop: vi.fn() }]
  const stream = { getAudioTracks: () => tracks, getTracks: () => tracks }
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn(async () => stream) } })
  vi.stubGlobal('MediaRecorder', class {
    state = 'inactive'; mimeType = 'audio/webm'
    ondataavailable: ((e: { data: Blob }) => void) | null = null; onstop: (() => void) | null = null
    start() { this.state = 'recording'; this.ondataavailable?.({ data: new Blob(['x']) }) }
    stop() { this.state = 'inactive'; this.onstop?.() }
  })
  vi.stubGlobal('AudioContext', class { constructor() { throw new Error('no audio in tests') } })
  vi.stubGlobal('RTCPeerConnection', class {
    connectionState = 'new'
    addTrack() {}
    createDataChannel() { return channel }
    async createOffer() { return { type: 'offer', sdp: 'offer-sdp' } }
    async setLocalDescription() {}
    async setRemoteDescription() { queueMicrotask(() => channel.onopen?.()) }
    addEventListener() {}
    close() { pcClosed = true }
  })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { cb(0); return 1 })
  vi.stubGlobal('cancelAnimationFrame', () => {})
  fetchMock = vi.fn(async (url: string) =>
    url === '/api/audio/live-session'
      ? new Response(JSON.stringify(SECRET))
      : new Response('answer-sdp'))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('live transcription', () => {
  it('pre-warms the secret once and reuses it', async () => {
    await prewarm(); await prewarm()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('streams text live, commits on stop, and returns the full transcript', async () => {
    const onText = vi.fn(), onState = vi.fn()
    const recording = await startLiveTranscription({ onText, onState })
    expect(onState.mock.calls.map(c => c[0])).toEqual(['connecting', 'listening'])
    const [, call] = fetchMock.mock.calls
    expect(call[0]).toBe('https://api.openai.com/v1/realtime/calls')
    expect(call[1].headers.Authorization).toBe('Bearer ek_test')
    expect(call[1].body).toBe('offer-sdp')

    channel.emit({ type: 'conversation.item.input_audio_transcription.delta', item_id: 'i1', delta: 'Police stopped ' })
    expect(onText).toHaveBeenLastCalledWith('', 'Police stopped')
    channel.emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'i1', transcript: 'Police stopped my brother' })
    expect(onText).toHaveBeenLastCalledWith('Police stopped my brother', '')

    const text = await recording.stop()
    expect(JSON.parse(channel.sent[0])).toEqual({ type: 'input_audio_buffer.commit' })
    expect(text).toBe('Police stopped my brother near Patna.')
    expect(tracks[0].stop).toHaveBeenCalled()
    expect(pcClosed).toBe(true)
  })

  it('falls back to uploading the recording when live mode is unavailable', async () => {
    fetchMock.mockImplementation(async () => new Response('', { status: 503 }))
    const transcribe = vi.spyOn(api, 'transcribe').mockResolvedValue({ transcript: ' Landlord kept my deposit ' })
    const recording = await startLiveTranscription({ onText: vi.fn() })
    expect(await recording.stop()).toBe('Landlord kept my deposit')
    expect(transcribe).toHaveBeenCalledOnce()
  })
})
