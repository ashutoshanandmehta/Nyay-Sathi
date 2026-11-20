/// <reference types="node" />
// @vitest-environment node
import { PGlite } from '@electric-sql/pglite'
import { afterAll, beforeAll, expect, it } from 'vitest'
import { createRequiredSemanticRetriever } from '../../supabase/functions/nyay-api/semantic-retrieval'
import type { SupabaseHybridRpcRow } from '../../supabase/functions/nyay-api/legal-retrieval'
import seed from '../../data/legal_corpus/v1/seed_legal_corpus.sql?raw'
import cases from './fixtures/legal-retrieval-qualification-cases.json'
import embeddings from './fixtures/openai-legal-query-embeddings.json'

const migrations=import.meta.glob('../../supabase/migrations/*.sql',{query:'?raw',import:'default',eager:true}) as Record<string,string>
let db:PGlite
const sql=async<T>(statement:string,args:unknown[]=[]) => (await db.query<T>(statement,args)).rows

beforeAll(async()=>{
  db=new PGlite()
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth; create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as
      $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    grant usage on schema public,auth to authenticated,anon,service_role;
  `)
  for(const path of Object.keys(migrations).sort()) await db.exec(migrations[path])
  await db.exec(seed)
},60_000)
afterAll(async()=>db?.close())

async function retrieve(query:string,incidentDate:string|null,region:string|null){
  const fixture=Object.values(embeddings).find(row=>row.query===query)
  expect(fixture?.embedding).toHaveLength(384)
  return createRequiredSemanticRetriever({
    embedder:async()=>fixture!.embedding,
    rpc:async(_name,args)=>sql<SupabaseHybridRpcRow>('select * from nyay_legal_hybrid_search($1,$2,$3,$4,$5,$6)',[
      args.p_query,args.p_query_embedding,args.p_region,args.p_incident_date,args.p_as_of_date,args.p_limit,
    ]),
    fetchPassagesByIds:ids=>sql<SupabaseHybridRpcRow>('select * from nyay_legal_passages where passage_id=any($1::text[])',[ids]),
  })({
    query,region,incidentDate,asOfDate:'2026-11-20',limit:6,
    dateBasis:incidentDate?'confirmed_incident':'general_current_law',
    signal:new AbortController().signal,
  })
}

it.each(cases)('passes the OpenAI SQL hybrid gate: $case_id',async testCase=>{
  const result=await retrieve(testCase.query,testCase.incident_date,testCase.region)
  const ids=result.passages.map(row=>row.passageId)
  if(testCase.expect_empty){
    expect(ids).toEqual([])
  }else{
    expect(testCase.expected_any_ids.some(id=>ids.includes(id))).toBe(true)
    expect(testCase.forbidden_ids.some(id=>ids.includes(id))).toBe(false)
  }
})

it('retrieves and cites current law without inventing an incident date',async()=>{
  const current=cases.find(row=>row.case_id==='exact_section_cpa_s35_companions')!
  const result=await retrieve(current.query,null,current.region)
  expect(result.passages.map(row=>row.passageId)).toContain('cpa2019-s35-complaint')
  expect(result.limitations.join(' ')).toContain('General information as of 2026-11-20')
})
