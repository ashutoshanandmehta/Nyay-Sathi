import { Capacitor } from '@capacitor/core'

export interface BackendConfig { mode: 'legacy' | 'supabase'; url?: string; key?: string }

export function backendConfig(): BackendConfig {
  const mode = import.meta.env.VITE_BACKEND || 'legacy'
  if (mode !== 'legacy' && mode !== 'supabase') throw new Error('Unsupported VITE_BACKEND setting.')
  if (mode === 'legacy') {
    if (Capacitor.isNativePlatform()) throw new Error('This Android build needs Supabase backend configuration.')
    return { mode }
  }
  const url = String(import.meta.env.VITE_SUPABASE_URL || '').replace(/\/$/, '')
  const key = String(import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '')
  let parsed: URL
  try { parsed = new URL(url) } catch { throw new Error('Set VITE_SUPABASE_URL before building the app.') }
  if (parsed.protocol !== 'https:' || parsed.pathname !== '/' || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error('VITE_SUPABASE_URL must be the HTTPS project origin.')
  }
  if (!key || key.startsWith('sb_secret_')) throw new Error('Use a Supabase publishable key, never a secret key, in the app.')
  // Legacy service-role JWTs must never be included in a client build either.
  if (key.split('.').length === 3) {
    try {
      const claims = JSON.parse(atob(key.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      if (claims.role !== 'anon') throw new Error('private key')
    } catch { throw new Error('Use a publishable or legacy anon key in the app.') }
  }
  return { mode, url, key }
}

// Only same-origin application requests are translated. Provider URLs and links
// opened from citations never receive application authentication credentials.
export function applicationPath(input: RequestInfo | URL): string | null {
  const value = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  try {
    const url = new URL(value, window.location.origin)
    return url.origin === window.location.origin && url.pathname.startsWith('/api/')
      ? url.pathname + url.search : null
  } catch { return null }
}
