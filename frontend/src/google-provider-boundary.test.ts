// @vitest-environment node
import { expect, it, vi } from 'vitest'
import { createNyayApiHandler, type DatabasePort } from '../../supabase/functions/nyay-api/handler'

const ownerId = 'owner'
const conversationId = 'owned-conversation'
const conversationPath = `/api/conversations/${conversationId}`
const googlePath = '/api/integrations/google'

function fixture() {
  // Legacy adapter methods exist even when Google itself is unavailable. Make
  // their access observable so an accidental fallback cannot simulate success.
  const legacyDatabaseCall = vi.fn(() => { throw new Error('Unexpected legacy provider database call') })
  const authorize = {
    authenticate: async (token: string | null) => token ? { id: token, is_anonymous: false } : null,
    getConversation: async (owner: string, id: string) =>
      owner === ownerId && id === conversationId ? { id, case_id: 'owned-case' } : null,
  }
  const db = new Proxy(authorize, {
    get(target, property) {
      return Reflect.has(target, property) ? Reflect.get(target, property) : legacyDatabaseCall
    },
  }) as unknown as DatabasePort
  const handler = createNyayApiHandler({ db })
  const request = (path: string, method = 'GET', token: string | null = ownerId, body?: unknown) =>
    handler(new Request(`https://test.example${path}`, {
      method,
      headers: token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : {},
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }))
  return { request, legacyDatabaseCall }
}

const operations = [
  ['POST', `${googlePath}/connect`, {
    provider: 'google_drive',
    provider_account_email: 'unverified@example.com',
    granted_scopes: ['https://www.googleapis.com/auth/drive.file'],
    access_token: 'fake',
  }],
  ['PATCH', `${googlePath}/gmail-monitoring`, { opted_in: true }],
  ['POST', `${conversationPath}/drive/folder`, { drive_folder_id: 'fake' }],
  ['POST', `${conversationPath}/drive/upload`, { drive_file_id: 'fake', filename: 'receipt.pdf' }],
  ['POST', `${conversationPath}/drive/reconcile`, { provider_file_states: { fake: 'present' } }],
  ['POST', `${conversationPath}/gmail/import`, { gmail_message_id: 'fake', subject: 'Email' }],
  ['POST', `${conversationPath}/gmail/approvals`, { subject: 'Email' }],
  ['POST', `${conversationPath}/gmail/send`, { approval_id: 'fake' }],
  ['POST', `${conversationPath}/gmail/reconcile`, { approval_id: 'fake', provider_sent_found: true }],
] as const

it.each(operations)('%s %s reports unavailable without accessing synthetic provider state', async (method, path, body) => {
  const { request, legacyDatabaseCall } = fixture()
  const response = await request(path, method, ownerId, body)
  expect(response.status).toBe(503)
  expect(await response.json()).toMatchObject({ code: 'google_provider_unavailable' })
  expect(legacyDatabaseCall).not.toHaveBeenCalled()
})

it('does not present synthetic historical connections, receipts or actions as provider state', async () => {
  const { request, legacyDatabaseCall } = fixture()
  const status = await request(`${googlePath}/status`)
  expect(await status.json()).toMatchObject({
    google_drive: null, google_gmail: null, availability: 'unavailable',
    storage_policy: 'disclosed_temporary_processing',
  })
  const drive = await request(`${conversationPath}/drive/manifest`)
  expect(await drive.json()).toMatchObject({ availability: 'unavailable', folder: null, items: [] })
  const gmail = await request(`${conversationPath}/gmail/state`)
  expect(await gmail.json()).toMatchObject({
    availability: 'unavailable', evidence_messages: [], approvals: [], dispatches: [],
  })
  expect(legacyDatabaseCall).not.toHaveBeenCalled()
})

it('requires authentication and case ownership even when provider execution is unavailable', async () => {
  const { request, legacyDatabaseCall } = fixture()
  expect((await request(`${googlePath}/status`, 'GET', null)).status).toBe(401)
  expect((await request(`${conversationPath}/drive/manifest`, 'GET', 'other-owner')).status).toBe(404)
  expect((await request(`${conversationPath}/gmail/send`, 'POST', 'other-owner', {})).status).toBe(404)
  expect(legacyDatabaseCall).not.toHaveBeenCalled()
})
