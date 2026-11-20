// @vitest-environment node
import migration from '../../supabase/migrations/20261119091306_android_backend_foundation.sql?raw'
import { PGlite } from '@electric-sql/pglite'
import { afterAll, beforeAll, expect, it } from 'vitest'

let db: PGlite
const alice = '11111111-1111-4111-8111-111111111111'
const bob = '22222222-2222-4222-8222-222222222222'
let aliceCase: string
let aliceChat: string

async function asUser(id: string) {
  await db.exec('reset role; set role authenticated;')
  await db.query("select set_config('request.jwt.claim.sub', $1, false)", [id])
}

beforeAll(async () => {
  db = new PGlite()
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as
      $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
    grant usage on schema public, auth to authenticated, anon, service_role;
    grant execute on function auth.uid() to authenticated, anon, service_role;
    insert into auth.users values ('${alice}'), ('${bob}');
  `)
  await db.exec(migration)
  await asUser(alice)
  const created = await db.query<{ value: { id: string; case_id: string } }>("select public.nyay_create_conversation('hi') as value")
  aliceChat = created.rows[0].value.id
  aliceCase = created.rows[0].value.case_id
}, 30_000)

afterAll(async () => { await db?.close() })

it('creates a case and chat atomically for the authenticated user', async () => {
  await asUser(alice)
  const cases = await db.query('select id from public.nyay_cases')
  expect(cases.rows).toEqual([{ id: aliceCase }])
  const chats = await db.query<{ language: string }>('select language from public.nyay_conversations')
  expect(chats.rows[0].language).toBe('hi')
})

it('another user cannot see, update, delete or attach a chat to the case', async () => {
  await asUser(bob)
  expect((await db.query('select * from public.nyay_cases')).rows).toEqual([])
  expect((await db.query('select * from public.nyay_conversations')).rows).toEqual([])
  expect((await db.query('update public.nyay_cases set title=$1 where id=$2 returning id', ['stolen', aliceCase])).rows).toEqual([])
  expect((await db.query('delete from public.nyay_conversations where id=$1 returning id', [aliceChat])).rows).toEqual([])
  await expect(db.query("select public.nyay_create_conversation('en', $1)", [aliceCase])).rejects.toThrow('Case not found')
})

it('an owner cannot transfer a case to another user through an update', async () => {
  await asUser(alice)
  await expect(db.query('update public.nyay_cases set owner_id=$1 where id=$2', [bob, aliceCase])).rejects.toThrow(/row-level security/)
})

it('clients cannot forge assistant messages, reviewed results or stream events', async () => {
  await asUser(alice)
  await expect(db.query("insert into public.nyay_messages(conversation_id,owner_id,request_id,role,content) values($1,$2,'forged','assistant','approved')", [aliceChat, alice])).rejects.toThrow(/permission denied/)
  await expect(db.query("insert into public.nyay_turn_executions(conversation_id,owner_id,request_id,payload_hash,status) values($1,$2,'forged','x','reviewed')", [aliceChat, alice])).rejects.toThrow(/permission denied/)
  await expect(db.query("insert into public.nyay_case_memory(case_id,owner_id,memory) values($1,$2,'{}')", [aliceCase, alice])).rejects.toThrow(/permission denied/)
})

it('unauthenticated clients cannot read cases or invoke case creation', async () => {
  await db.exec('reset role; set role anon;')
  await expect(db.query('select * from public.nyay_cases')).rejects.toThrow(/permission denied/)
  await expect(db.query('select public.nyay_create_conversation()')).rejects.toThrow(/permission denied/)
})

it('rejects invalid language without leaving an orphan case', async () => {
  await asUser(alice)
  await expect(db.query("select public.nyay_create_conversation('invalid')")).rejects.toThrow('Unsupported language')
  expect((await db.query('select * from public.nyay_cases')).rows).toHaveLength(1)
})

it('enforces one active turn per conversation and unique replay identities', async () => {
  await db.exec('reset role;')
  const insert = "insert into public.nyay_turn_executions(conversation_id,owner_id,request_id,payload_hash,status) values($1,$2,$3,'digest','running')"
  await db.query(insert, [aliceChat, alice, 'request-1'])
  await expect(db.query(insert, [aliceChat, alice, 'request-2'])).rejects.toThrow(/duplicate key/)
  await db.query("update public.nyay_turn_executions set status='completed' where request_id='request-1'")
  await expect(db.query(insert, [aliceChat, alice, 'request-1'])).rejects.toThrow(/duplicate key/)
  await db.query(insert, [aliceChat, alice, 'request-2'])
})
