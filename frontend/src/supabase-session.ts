import { createClient, type SupabaseClient, type SupportedStorage } from '@supabase/supabase-js'

export interface NativeSecureStorageBridge {
  getItem(key: string): Promise<string | null> | string | null
  setItem(key: string, value: string): Promise<void> | void
  removeItem(key: string): Promise<void> | void
}

declare global {
  interface Window {
    NyayNativeSecureStorage?: NativeSecureStorageBridge
  }
}

const memoryFallback = new Map<string, string>()

/**
 * Pluggable storage adapter: prefers Android native secure storage bridge when available,
 * falling back to WebView/browser localStorage and in-memory map if storage is restricted.
 */
export const secureAuthStorage: SupportedStorage = {
  async getItem(key: string): Promise<string | null> {
    if (typeof window !== 'undefined' && window.NyayNativeSecureStorage) {
      return await window.NyayNativeSecureStorage.getItem(key)
    }
    try {
      return localStorage.getItem(key)
    } catch {
      return memoryFallback.get(key) ?? null
    }
  },
  async setItem(key: string, value: string): Promise<void> {
    if (typeof window !== 'undefined' && window.NyayNativeSecureStorage) {
      await window.NyayNativeSecureStorage.setItem(key, value)
      return
    }
    try {
      localStorage.setItem(key, value)
    } catch {
      memoryFallback.set(key, value)
    }
  },
  async removeItem(key: string): Promise<void> {
    if (typeof window !== 'undefined' && window.NyayNativeSecureStorage) {
      await window.NyayNativeSecureStorage.removeItem(key)
      return
    }
    try {
      localStorage.removeItem(key)
    } catch {
      memoryFallback.delete(key)
    }
  },
}

let client: SupabaseClient | undefined
let initializing: Promise<string> | undefined

export function getSupabaseClient(url: string, key: string): SupabaseClient {
  client ||= createClient(url, key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
      storage: secureAuthStorage,
    },
  })
  return client
}

export async function supabaseAccessToken(url: string, key: string): Promise<string> {
  const sb = getSupabaseClient(url, key)
  // Bootstrap/list can run together. Create only one guest identity per install.
  if (!initializing) {
    initializing = (async () => {
      const { data, error } = await sb.auth.getSession()
      if (error) throw new Error('Could not restore your session. Please retry.')
      if (data.session) return data.session.access_token
      const signed = await sb.auth.signInAnonymously()
      if (signed.error || !signed.data.session) {
        throw new Error('Could not start your session. Check that anonymous sign-in is enabled.')
      }
      return signed.data.session.access_token
    })()
  }
  try {
    return await initializing
  } finally {
    initializing = undefined
  }
}

/**
 * Upgrades the current anonymous guest session in-place to a permanent account.
 * Preserves the exact same auth.uid() so existing cases/conversations remain owned by this user
 * and never moves or merges another user's records.
 */
export async function upgradeGuestAccount(
  url: string,
  key: string,
  credentials: { email: string; password?: string }
): Promise<{ userId: string; email: string }> {
  const sb = getSupabaseClient(url, key)
  const { data: sessionData, error: sessionErr } = await sb.auth.getSession()
  if (sessionErr || !sessionData.session?.user) {
    throw new Error('No active session to upgrade. Start a guest session first.')
  }
  const currentUser = sessionData.session.user
  const trimmedEmail = credentials.email.trim()
  if (!trimmedEmail || !trimmedEmail.includes('@')) {
    throw new Error('Enter a valid email address to link your account.')
  }
  const { data, error } = await sb.auth.updateUser({
    email: trimmedEmail,
    ...(credentials.password ? { password: credentials.password } : {}),
  })
  if (error || !data.user) {
    throw new Error(error?.message || 'Could not link this email address.')
  }
  if (data.user.id !== currentUser.id) {
    throw new Error('Account identity mismatch detected during link; operation aborted.')
  }
  return { userId: data.user.id, email: trimmedEmail }
}

export function resetSupabaseSessionForTesting(): void {
  client = undefined
  initializing = undefined
  memoryFallback.clear()
}
