import { afterEach, describe, expect, it, vi } from 'vitest'
import { applicationPath, backendConfig } from './backend'
import { apiFetch, UNLOCK_HEADER } from './byok'

vi.mock('./supabase-session', () => ({ supabaseAccessToken: vi.fn(async () => 'session-token') }))

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

describe('Supabase API transport', () => {
  function configured() {
    vi.stubEnv('VITE_BACKEND', 'supabase')
    vi.stubEnv('VITE_SUPABASE_URL', 'https://example.supabase.co')
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_example')
  }

  it('keeps web development on its existing backend', () => {
    vi.stubEnv('VITE_BACKEND', '')
    expect(backendConfig()).toEqual({ mode: 'legacy' })
  })

  it.each(['http://example.com', 'https://example.com/functions/v1', 'https://user:password@example.com', 'https://example.com?key=secret'])('rejects an unsafe project URL: %s', url => {
    configured(); vi.stubEnv('VITE_SUPABASE_URL', url)
    expect(() => backendConfig()).toThrow('HTTPS project origin')
  })

  it.each(['sb_secret_private', `a.${btoa(JSON.stringify({ role: 'service_role' }))}.c`])('rejects private frontend keys', key => {
    configured(); vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', key)
    expect(() => backendConfig()).toThrow(/publishable|secret/)
  })

  it('maps only our API path to the function and authenticates without cookies', async () => {
    configured()
    const fetcher = vi.fn(async () => new Response('{}'))
    vi.stubGlobal('fetch', fetcher)
    await apiFetch('/api/conversations/c/turns/stream?retry=1', {
      method: 'POST', body: '{"question":"help"}', credentials: 'include', headers: { 'X-CSRF-Token': 'browser-cookie', 'Content-Type': 'application/json' },
    })
    const [request, init] = fetcher.mock.calls[0] as unknown as [Request, RequestInit]
    expect(request.url).toBe('https://example.supabase.co/functions/v1/nyay-api/api/conversations/c/turns/stream?retry=1')
    expect(init.credentials).toBe('omit')
    expect(init.redirect).toBe('error')
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer session-token')
    expect(headers.get('apikey')).toBe('sb_publishable_example')
    expect(headers.has('X-CSRF-Token')).toBe(false)
    expect(init.body).toBe('{"question":"help"}')
  })

  it('never leaks a session or unlock secret to provider or citation URLs', async () => {
    configured()
    const fetcher = vi.fn(async () => new Response('{}'))
    vi.stubGlobal('fetch', fetcher)
    for (const url of ['https://api.openai.com/v1/realtime/calls', 'https://example.supabase.co.evil.test/api/data', 'https://example.supabase.co/functions/v1/nyay-api/api/data']) {
      await apiFetch(url)
      const [, init] = fetcher.mock.calls.at(-1) as unknown as [RequestInfo, RequestInit | undefined]
      const headers = new Headers(init?.headers)
      expect(headers.has('Authorization')).toBe(false)
      expect(headers.has(UNLOCK_HEADER)).toBe(false)
    }
  })

  it('preserves Request method, body, headers and cancellation', async () => {
    configured()
    const fetcher = vi.fn(async () => new Response('{}'))
    vi.stubGlobal('fetch', fetcher)
    const abort = new AbortController()
    const original = new Request(new URL('/api/upload', window.location.origin), { method: 'POST', body: 'evidence', headers: { 'X-Example': 'keep' }, signal: abort.signal })
    await apiFetch(original)
    const [mapped, init] = fetcher.mock.calls[0] as unknown as [Request, RequestInit]
    expect(mapped.method).toBe('POST')
    expect(await mapped.text()).toBe('evidence')
    expect(new Headers(init.headers).get('X-Example')).toBe('keep')
    abort.abort()
    expect(mapped.signal.aborted).toBe(true)
  })

  it('does not treat /api lookalikes as application routes', () => {
    expect(applicationPath('/api-evil/data')).toBeNull()
    expect(applicationPath('/somewhere')).toBeNull()
  })
})
