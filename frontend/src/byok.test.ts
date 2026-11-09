import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UNLOCK_HEADER, apiFetch, unlockSecret } from './byok'

describe('own-key unlock secret', () => {
  const fetchMock = vi.fn(async () => new Response('{}'))
  beforeEach(() => { localStorage.clear(); fetchMock.mockClear(); vi.stubGlobal('fetch', fetchMock) })
  afterEach(() => vi.unstubAllGlobals())

  const sentHeaders = (call = 0) => new Headers((fetchMock.mock.calls[call] as unknown as [RequestInfo, RequestInit])[1].headers)

  it('is a random 32-byte secret created once per browser', () => {
    const first = unlockSecret()
    expect(first).toMatch(/^[A-Za-z0-9_-]{43}$/)
    expect(unlockSecret()).toBe(first)
    localStorage.clear()
    expect(unlockSecret()).not.toBe(first)
  })

  it('goes with every request to our API, keeping the caller headers', async () => {
    await apiFetch('/api/conversations', { headers: { 'X-CSRF-Token': 't' } })
    expect(sentHeaders().get(UNLOCK_HEADER)).toBe(unlockSecret())
    expect(sentHeaders().get('X-CSRF-Token')).toBe('t')
  })

  it('never goes to another site, such as OpenAI', async () => {
    await apiFetch('https://api.openai.com/v1/realtime/calls', { method: 'POST' })
    await apiFetch('/not-api/page')
    expect(sentHeaders(0).has(UNLOCK_HEADER)).toBe(false)
    expect(sentHeaders(1).has(UNLOCK_HEADER)).toBe(false)
  })
})
