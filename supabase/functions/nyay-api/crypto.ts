// Maintained WebCrypto AEAD (AES-256-GCM + HKDF-SHA256 / PBKDF2-SHA256)
// Replaces the legacy bespoke SHAKE/HMAC construction while preserving BYOK sealing and transfer bundle semantics.

const encoder = new TextEncoder()
const decoder = new TextDecoder()

export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

export function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function base64UrlToBytes(input: string): Uint8Array {
  const padded = input.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((input.length + 3) % 4)
  const binary = atob(padded)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i)
  return out
}

export async function sha256Hex(input: string | Uint8Array): Promise<string> {
  const data = typeof input === 'string' ? encoder.encode(input) : input
  const digest = await crypto.subtle.digest('SHA-256', data as BufferSource)
  return bytesToHex(new Uint8Array(digest))
}

function sortDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortDeep)
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b))
    const sorted: Record<string, unknown> = {}
    for (const [k, v] of entries) sorted[k] = sortDeep(v)
    return sorted
  }
  return value
}

export async function canonicalPayloadHash(payload: unknown): Promise<string> {
  return sha256Hex(JSON.stringify(sortDeep(payload)))
}

export function parseUnlockSecret(headerValue: string | null | undefined): Uint8Array | null {
  if (!headerValue || typeof headerValue !== 'string') return null
  const trimmed = headerValue.trim()
  if (trimmed.length < 32 || trimmed.length > 128 || !/^[A-Za-z0-9_-]+$/.test(trimmed)) return null
  try {
    const raw = base64UrlToBytes(trimmed)
    return raw.length >= 24 && raw.length <= 64 ? raw : null
  } catch {
    return null
  }
}

export function keyHint(apiKey: string): string {
  const trimmed = apiKey.trim()
  return `••••${trimmed.slice(-4)}`
}

async function deriveByokKey(
  unlockSecret: Uint8Array,
  ownerId: string,
  serverSecret: string,
  salt: Uint8Array
): Promise<CryptoKey> {
  const ikm = new Uint8Array(unlockSecret.length + serverSecret.length + 1)
  ikm.set(unlockSecret, 0)
  ikm[unlockSecret.length] = 0x3a
  ikm.set(encoder.encode(serverSecret), unlockSecret.length + 1)

  const baseKey = await crypto.subtle.importKey('raw', ikm as BufferSource, 'HKDF', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: salt as BufferSource,
      info: encoder.encode(`nyay-byok-aead-v1:${ownerId}`) as BufferSource,
    },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  )
}

export async function sealApiKey(
  apiKey: string,
  unlockSecret: Uint8Array,
  ownerId: string,
  serverSecret: string
): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const aesKey = await deriveByokKey(unlockSecret, ownerId, serverSecret, salt)
  const aad = encoder.encode(`owner:${ownerId}`)
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv as BufferSource, additionalData: aad as BufferSource },
    aesKey,
    encoder.encode(apiKey) as BufferSource
  )
  return `aead:v1:${bytesToBase64Url(salt)}:${bytesToBase64Url(iv)}:${bytesToBase64Url(new Uint8Array(ciphertext))}`
}

export async function unsealApiKey(
  sealed: string,
  unlockSecret: Uint8Array | null,
  ownerId: string,
  serverSecret: string
): Promise<string | null> {
  if (!unlockSecret || !sealed.startsWith('aead:v1:')) return null
  const parts = sealed.split(':')
  if (parts.length !== 5) return null
  try {
    const salt = base64UrlToBytes(parts[2])
    const iv = base64UrlToBytes(parts[3])
    const ciphertext = base64UrlToBytes(parts[4])
    const aesKey = await deriveByokKey(unlockSecret, ownerId, serverSecret, salt)
    const aad = encoder.encode(`owner:${ownerId}`)
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: iv as BufferSource, additionalData: aad as BufferSource },
      aesKey,
      ciphertext as BufferSource
    )
    return decoder.decode(plaintext)
  } catch {
    return null
  }
}

export interface EncryptedTransferBundle {
  format: 'nyay-transfer-aead-v2'
  kdf: 'PBKDF2-SHA256'
  iterations: number
  cipher: 'AES-256-GCM'
  salt: string
  iv: string
  ciphertext: string
  exported_at: string
  loss_warning: string
}

async function derivePassphraseKey(passphrase: string, salt: Uint8Array, iterations = 120_000): Promise<CryptoKey> {
  const baseKey = await crypto.subtle.importKey(
    'raw',
    encoder.encode(passphrase) as BufferSource,
    'PBKDF2',
    false,
    ['deriveKey']
  )
  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      hash: 'SHA-256',
      salt: salt as BufferSource,
      iterations,
    },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  )
}

export async function exportEncryptedTransferBundle(
  snapshot: Record<string, unknown>,
  passphrase: string
): Promise<EncryptedTransferBundle> {
  if (!passphrase || passphrase.length < 8) {
    throw new Error('Passphrase must be at least 8 characters')
  }
  const iterations = 120_000
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await derivePassphraseKey(passphrase, salt, iterations)
  const aad = encoder.encode('nyay-transfer-aead-v2')
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv as BufferSource, additionalData: aad as BufferSource },
    key,
    encoder.encode(JSON.stringify(snapshot)) as BufferSource
  )
  return {
    format: 'nyay-transfer-aead-v2',
    kdf: 'PBKDF2-SHA256',
    iterations,
    cipher: 'AES-256-GCM',
    salt: bytesToBase64Url(salt),
    iv: bytesToBase64Url(iv),
    ciphertext: bytesToBase64Url(new Uint8Array(ciphertext)),
    exported_at: new Date().toISOString(),
    loss_warning:
      'Keep both this transfer bundle and your passphrase safe. Without the passphrase, encrypted case contents cannot be recovered.',
  }
}

export async function importEncryptedTransferBundle(
  bundle: Record<string, unknown>,
  passphrase: string
): Promise<Record<string, unknown>> {
  if (!passphrase || passphrase.length < 8) {
    throw new Error('Invalid passphrase or corrupted transfer bundle')
  }
  if (bundle?.format !== 'nyay-transfer-aead-v2' || typeof bundle.salt !== 'string' || typeof bundle.iv !== 'string' || typeof bundle.ciphertext !== 'string') {
    throw new Error('Unsupported or corrupted transfer bundle format')
  }
  try {
    const iterations = typeof bundle.iterations === 'number' && bundle.iterations >= 10_000 ? bundle.iterations : 120_000
    const salt = base64UrlToBytes(bundle.salt)
    const iv = base64UrlToBytes(bundle.iv)
    const ciphertext = base64UrlToBytes(bundle.ciphertext)
    const key = await derivePassphraseKey(passphrase, salt, iterations)
    const aad = encoder.encode('nyay-transfer-aead-v2')
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: iv as BufferSource, additionalData: aad as BufferSource },
      key,
      ciphertext as BufferSource
    )
    return JSON.parse(decoder.decode(plaintext)) as Record<string, unknown>
  } catch {
    throw new Error('Decryption failed: wrong passphrase or tampered transfer package')
  }
}
