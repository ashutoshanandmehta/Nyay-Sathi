// Your own OpenAI key: the server stores it sealed with a secret that only this browser keeps.
// Every request to our /api sends that secret so the server can open the key for that request;
// requests to anyone else (e.g. OpenAI's WebRTC endpoint) never get it.

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

function sameOriginApi(input: RequestInfo | URL): boolean {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/')
  } catch {
    return false
  }
}

/** fetch for our own API: adds the unlock secret; any other URL is fetched unchanged. */
export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  if (!sameOriginApi(input)) return fetch(input, init)
  const headers = new Headers(init.headers)
  headers.set(UNLOCK_HEADER, unlockSecret())
  return fetch(input, { ...init, headers })
}
