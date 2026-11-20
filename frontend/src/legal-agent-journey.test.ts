/// <reference types="node" />
// @vitest-environment node
import { PGlite } from '@electric-sql/pglite'
import { afterAll, beforeAll, expect, it, vi } from 'vitest'
import { defaultCaseMemory } from '../../supabase/functions/nyay-api/contracts'
import type { BackgroundProvider, ModelInput } from '../../supabase/functions/nyay-api/background-provider'
import { createResumableHandler } from '../../supabase/functions/nyay-api/resumable-http'
import { createOpenAiQueryEmbedder, createRequiredSemanticRetriever, createVersionedQueryEmbedder } from '../../supabase/functions/nyay-api/semantic-retrieval'
import { retrievalDateBasis } from '../../supabase/functions/nyay-api/retrieval-port'
import type { SupabaseHybridRpcRow } from '../../supabase/functions/nyay-api/legal-retrieval'
import seed from '../../data/legal_corpus/v1/seed_legal_corpus.sql?raw'
import embeddingFixtures from './fixtures/openai-legal-query-embeddings.json'
import { LEGAL_CORPUS_BUNDLE } from '../../supabase/functions/nyay-api/legal-corpus-data'

const migrations=import.meta.glob('../../supabase/migrations/*.sql',{query:'?raw',import:'default',eager:true}) as Record<string,string>
const scenarios=[
  {lang:'en',date:'2025-02-01',query:'Section 35 Consumer Protection Act 2019 filing complaint in District Commission',id:'cpa2019-s35-complaint'},
  {lang:'hi',date:'2025-02-01',query:'मेरा ऑनलाइन खरीदा हुआ सामान खराब निकला और कंपनी पैसे वापस नहीं कर रही',id:'ecommerce-r6-refund',alternates:['ecommerce-r7-inventory-refund','cpa2019-s39-relief']},
  {lang:'hinglish',date:'2025-02-01',query:'UPI se paise kat gaye par samne wale ko nahi mile, bank kab tak wapas karega aur muavza kitna milega',id:'rbi-2019-failed-tx-tat-rules'},
  {lang:'en',date:'2023-06-01',query:'Cheating and dishonestly inducing delivery of money and FIR registration for financial fraud',id:'ipc1860-s420-historical'},
  {lang:'en',date:null,query:'What is the procedure for mutual consent divorce and child custody under Hindu Marriage Act?',id:null},
  {lang:'en',date:null,query:'My payment failed yesterday. What are the current rules?',id:null},
] as const
const owner='11111111-1111-4111-8111-111111111111'
const origin='http://localhost/nyay-api'
let db:PGlite
let vectors:Record<string,number[]>
const sql=async<T>(statement:string,args:unknown[]=[]) => (await db.query<T>(statement,args)).rows
const rpc=async<T>(name:string,args:Record<string,unknown>={}) =>
  (await sql<{value:T}>(`select public.${name}(${Object.keys(args).map((k,i)=>k+' => $'+(i+1)).join(',')}) value`,Object.values(args)))[0].value

beforeAll(async()=>{
  const queries=scenarios.slice(0,4).map(s=>s.query)
  const fixtures=Object.values(embeddingFixtures) as Array<{query:string;embedding:number[]}>
  vectors=Object.fromEntries(queries.map(query=>[query,fixtures.find(row=>row.query===query)?.embedding])) as Record<string,number[]>
  expect(Object.values(vectors).every(vector=>vector?.length===384)).toBe(true)
  db=new PGlite()
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth; create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as
      $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    grant usage on schema public,auth to authenticated,anon,service_role;
    insert into auth.users values ('${owner}');
  `)
  for(const path of Object.keys(migrations).sort()) await db.exec(migrations[path])
  await db.exec(seed)
},60_000)
afterAll(async()=>{await db?.close()})

it.each(scenarios)('retrieves, reviews and replays $lang ($date) for $id',async scenario=>{
  // Each case represents a separate pilot day to retain the real per-day reservation logic.
  await db.exec('truncate nyay_usage_budgets')
  const [chat]=await sql<{id:string}>(`with c as (insert into nyay_cases(owner_id,incident_date) values($1,$2) returning id)
    insert into nyay_conversations(owner_id,case_id,language) select $1,id,$3 from c returning id`,[owner,scenario.date,scenario.lang])
  const path='/api/conversations/'+chat.id+'/turns'
  const submissions=new Map<string,ModelInput>()
  const embedded:string[]=[]
  let semanticRows=0
  let citedId:string|null=scenario.id
  const retrieve=createRequiredSemanticRetriever({
    async embedder(query) { embedded.push(query);return vectors[query] || null },
    async rpc(_name,args) {
      const rows=await sql<SupabaseHybridRpcRow>('select * from nyay_legal_hybrid_search($1,$2,$3,$4,$5,$6)',[
        args.p_query,args.p_query_embedding,args.p_region,args.p_incident_date,args.p_as_of_date,args.p_limit,
      ])
      semanticRows+=rows.filter(row=>Number(row.semantic_rank)>0).length
      return rows
    },
    fetchPassagesByIds:ids=>sql<SupabaseHybridRpcRow>('select * from nyay_legal_passages where passage_id=any($1::text[])',[ids]),
  })
  const answer={
    central_question:scenario.query,risk:'ordinary',case_stage:'intake',next_action:'Review the source',
    factual_issues:[],legal_issues:[],case_patches:[],
    tasks:[{task_id:'legal',title:'Legal information',intent:'information',domain:'consumer',case_link:'unrelated',source_segment_ids:[]}],
    claims:[] as Array<Record<string,unknown>>,
  }
  const provider:BackgroundProvider={
    async submit(_key,args) {
      expect(args.runtime).toMatchObject({model:'gpt-6.2-sol',reasoning:'medium'})
      const ref='resp_'+submissions.size+chat.id.replaceAll('-','')
      submissions.set(ref,args)
      return ref
    },
    async collect(_key,id) {
      const call=submissions.get(id)!
      const input=JSON.parse(String(call.input[0].content))
      let output:unknown
      if(call.stage==='primary') {
        expect(input.incident_date).toEqual(scenario.date)
        const expectedBasis=scenario.date ? 'confirmed_incident'
          : scenario.query.startsWith('My') ? 'incident_date_required' : 'general_current_law'
        expect(input.date_basis).toBe(expectedBasis)
        expect(input.law_as_of_date).toBe(expectedBasis==='general_current_law'?'2026-11-20':null)
        if(!scenario.id) expect(input.limitations.join(' ')).toMatch(
          expectedBasis==='incident_date_required' ? /incident date is unconfirmed/ : /outside the supported prototype scope/,
        )
        if(scenario.id) {
          const allowed=[scenario.id,...('alternates' in scenario?scenario.alternates:[])]
          citedId=allowed.find(candidate=>input.evidence[candidate]) || null
          expect(citedId).not.toBeNull()
          const source=input.evidence[citedId!]
          expect(source?.canonical_url).toMatch(/^https:/)
          if(scenario.date==='2023-06-01') {
            expect(Object.keys(input.evidence).some(id=>id.startsWith('bns2023-') || id.startsWith('bnss2023-'))).toBe(false)
          }
          answer.claims=[{claim_id:'grounded',task_id:'legal',kind:'legal',block_type:'direct_answer',
            grounding:'verified_legal_source',text:source.text.split(/\n\n/)[0],evidence_ids:[citedId],
            depends_on:[],optional:false,in_document:false}]
        } else {
          expect(Object.values(input.evidence).filter((e:any)=>e.kind==='public')).toEqual([])
        }
        output=answer
      } else {
        expect(call.stage).toBe('review')
        expect(input.pending_claim_ids).toEqual(scenario.id?['grounded']:[])
        output={
          claims:scenario.id?[{claim_id:'grounded',support:'supported',reason:'Exact retrieved passage',
            requires_public_evidence:true}]:[],
          patch_verdicts:[],primary_question_answered:Boolean(scenario.id),next_action_useful:Boolean(scenario.id),
          cross_block_coherent:true,repair_instructions:[],
        }
      }
      return {id,status:'completed',output:[{type:'message',role:'assistant',status:'completed',
        content:[{type:'output_text',text:JSON.stringify(output)}]}],
      usage:{input_tokens:1000,output_tokens:120,total_tokens:1120}}
    },
    async cancel() {},
  }
  const makeHandler=()=>createResumableHandler({
    rpc,retrieve,provider,key:'test',scheduleSecret:'worker',webhookSecret:'',
    authenticate:async token=>token===owner?{id:owner}:null,
    async prepare(job) {
      const [row]=await sql<{incident_date:string|null}>(`select c.incident_date::text from nyay_cases c
        join nyay_conversations v on v.case_id=c.id join nyay_turn_executions t on t.conversation_id=v.id where t.id=$1`,[job.execution_id])
      return {requestId:'legal-journey',region:null,incidentDate:row.incident_date,asOfDate:'2026-11-20',
        priorMessages:[],attachments:[],urgent:false,
        memory:{version:0,memory:defaultCaseMemory(),summary:'',staged_patches:[],case_proposals:[],quality_review_consent:false}}
    },
    async read(user,conversation,requestId) {
      return (await sql<any>('select id as execution_id,status,result from nyay_turn_executions where owner_id=$1 and conversation_id=$2 and request_id=$3',
        [user,conversation,requestId]))[0] || null
    },
    events:(user,id,after)=>sql<any>('select * from nyay_turn_events where owner_id=$1 and execution_id=$2 and seq>$3 order by seq',[user,id,after]),
  },async()=>new Response(null,{status:204}))
  const send=(route:string,token:string,body?:unknown)=>makeHandler()(new Request(origin+route,{
    method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token},
    body:body===undefined?undefined:JSON.stringify(body),
  }))
  const admission=await send(path,owner,{request_id:'legal-journey',content:scenario.query,language:scenario.lang,attachment_ids:[]})
  expect(admission.status).toBe(202)
  const eventsPath=path+'/legal-journey/events'
  const first=await (await send(eventsPath,owner)).json()
  expect(first.events).toHaveLength(1)
  for(let i=0;i<14;i++){
    await db.exec('update nyay_turn_work set due_at=clock_timestamp() where lease_until is null')
    const response=await send('/internal/resumable/sweep','worker',{})
    expect(response.status).toBe(200)
    if(!(await response.json()).processed) break
  }
  const replay=await (await send(eventsPath+'?after_seq='+first.events[0].seq,owner)).json()
  expect(replay.turn.status).toBe('completed')
  expect([...submissions.values()].map(call=>call.stage)).toEqual(['primary','review'])
  expect(replay.events.filter((event:any)=>event.kind==='result')).toHaveLength(1)
  expect(replay.turn.result.verification.independent_review_performed).toBe(true)
  if(scenario.id) {
    expect(embedded).toEqual([scenario.query])
    expect(semanticRows).toBeGreaterThan(0)
    expect(replay.turn.result.sources[0].passage_id).toBe(citedId)
    expect(replay.turn.result.assistant_message.content).toContain('[1](#cite-1)')
  } else {
    expect(embedded).toEqual([])
    expect(replay.turn.result.sources).toEqual([])
    expect(replay.turn.result.assistant_message.metadata.publication_status).toBe('fallback')
  }
},20_000)

it('rejects missing or mismatched embeddings before SQL can fall back to lexical search',async()=>{
  const rpc=vi.fn(async()=>[])
  const request={query:'What are rules for defective product refunds?',dateBasis:'general_current_law' as const,
    region:null,incidentDate:null,asOfDate:'2026-11-20',limit:6,signal:new AbortController().signal}
  const retrieve=createRequiredSemanticRetriever({rpc,fetchPassagesByIds:async()=>[],embedder:async()=>null})
  await expect(retrieve(request)).rejects.toThrow('Semantic legal retrieval is unavailable')
  expect(rpc).not.toHaveBeenCalled()
  const embed=createVersionedQueryEmbedder('https://embedding.example.invalid/e5','fixture')
  vi.stubGlobal('fetch',vi.fn(async()=>Response.json({model:'another-model',version:'x',embedding:Array(384).fill(0)})))
  try {
    await expect(embed(request.query,request.signal)).rejects.toThrow('model mismatch')
  } finally {vi.unstubAllGlobals()}
})

it('distinguishes general from incident-specific questions in Hindi and Hinglish',()=>{
  expect(retrievalDateBasis('उपभोक्ता शिकायत के लिए वर्तमान नियम क्या हैं?',null)).toBe('general_current_law')
  expect(retrievalDateBasis('UPI refund ke kya niyam hain?',null)).toBe('general_current_law')
  expect(retrievalDateBasis('मेरा भुगतान कल विफल हुआ। वर्तमान नियम क्या हैं?',null)).toBe('incident_date_required')
  expect(retrievalDateBasis('Mere UPI transfer ke paise kat gaye, kya niyam hain?',null)).toBe('incident_date_required')
})

it('restricts the hybrid SQL endpoint to the service role',async()=>{
  await db.exec('set role authenticated')
  try {
    await expect(db.query("select * from nyay_legal_hybrid_search('fixture')")).rejects.toThrow('permission denied')
  } finally { await db.exec('reset role') }
})

it('sends an artifact-pinned query request and accepts a real matching vector',async()=>{
  const query=scenarios[0].query
  const model='text-embedding-3-small'
  const request=vi.fn(async (_url:string,_init:RequestInit)=>Response.json({model,data:[
    {index:0,embedding:LEGAL_CORPUS_BUNDLE.manifest.embedding_canary.embedding},
    {index:1,embedding:vectors[query]},
  ]}))
  vi.stubGlobal('fetch',request)
  try {
    const embed=createOpenAiQueryEmbedder('fixture')
    const embedded=await embed(query,new AbortController().signal)
    expect(embedded).toHaveLength(384)
    expect(embedded?.[0]).toBeCloseTo(vectors[query][0],7)
    const [url,init]=request.mock.calls[0]
    expect(url).toBe('https://api.openai.com/v1/embeddings')
    expect(init.redirect).toBe('error')
    expect(JSON.parse(String(init.body))).toEqual({model,input:[LEGAL_CORPUS_BUNDLE.manifest.embedding_canary.input,query],dimensions:384,encoding_format:'float'})
  } finally {vi.unstubAllGlobals()}
})
