import { backendConfig, applicationPath } from './backend'

export const UNLOCK_HEADER = 'X-Nyay-Key-Unlock'
const STORAGE_KEY = 'nyay.keyUnlock'
let memorySecret = ''

function makeSecret(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** This browser's unlock secret, created once. Clearing site data loses it (the key is re-entered). */
export function unlockSecret(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return saved
    const fresh = memorySecret || makeSecret()
    localStorage.setItem(STORAGE_KEY, fresh)
    return fresh
  } catch {
    // Private windows can block storage; the key then works until the tab closes.
    memorySecret ||= makeSecret()
    return memorySecret
  }
}

/** fetch for our own API: adds the unlock secret; any other URL is fetched unchanged. */
export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const path = applicationPath(input)
  if (!path) return fetch(input, init)
  const config = backendConfig()
  const original = input instanceof Request ? input : undefined
  const headers = new Headers(init.headers || original?.headers)
  headers.set(UNLOCK_HEADER, unlockSecret())
  if (config.mode === 'supabase') {
    const { supabaseAccessToken } = await import('./supabase-session')
    headers.delete('X-CSRF-Token')
    headers.set('Authorization', `Bearer ${await supabaseAccessToken(config.url!, config.key!)}`)
    headers.set('apikey', config.key!)
    const inherited: RequestInit = original ? {
      method: original.method,
      body: ['GET', 'HEAD'].includes(original.method) ? undefined : await original.clone().arrayBuffer(),
      signal: original.signal, cache: original.cache, referrerPolicy: original.referrerPolicy,
    } : {}
    return fetch(new Request(`${config.url}/functions/v1/nyay-api${path}`, inherited), {
      ...init, headers, credentials: 'omit', redirect: 'error',
    })
  }
  return fetch(input, { ...init, headers })
}
