// @vitest-environment node
import { PGlite } from '@electric-sql/pglite'
import { afterAll, beforeAll, expect, it } from 'vitest'
import { createResumableHandler, turnWorkStore } from '../../supabase/functions/nyay-api/resumable-http'
import { defaultCaseMemory } from '../../supabase/functions/nyay-api/contracts'
import { applicablePassages } from '../../supabase/functions/nyay-api/retrieval-port'
import type { BackgroundProvider, ModelInput } from '../../supabase/functions/nyay-api/background-provider'
import { refundEvidence, bankingEvidence, retiredEvidence, regionalEvidence } from './fixtures/legal-retrieval'
import { verifyCompletionWebhook } from '../../supabase/functions/nyay-api/provider-webhook'
import { DEFAULT_RUNTIME, callReserve, runReserve, runtimeConfig, usageCost } from '../../supabase/functions/nyay-api/runtime-config'

const migrations=import.meta.glob('../../supabase/migrations/*.sql',{query:'?raw',import:'default',eager:true}) as Record<string,string>
const owner='11111111-1111-4111-8111-111111111111'
const stranger='22222222-2222-4222-8222-222222222222'
let db:PGlite
let chat:string
const base='http://localhost/nyay-api'
let now=0
let calls:Array<{id:string;args:ModelInput;at:number}>=[]
const cancelled:string[]=[]
const claim = {
  claim_id:'supported',task_id:'task',kind:'legal',block_type:'direct_answer',
  grounding:'verified_legal_source',text:refundEvidence.text,evidence_ids:[refundEvidence.passageId],
  optional:false,depends_on:[],in_document:false,
}
const unsupported={...claim,claim_id:'unsupported',text:'The store must award a cash penalty.',evidence_ids:['invented']}
const answer={
  central_question:'What remedy can I request?',risk:'ordinary',case_stage:'intake',next_action:'Ask the seller',
  factual_issues:[],legal_issues:[],case_patches:[],
  tasks:[{task_id:'task',title:'Consumer refund',intent:'legal_options',domain:'consumer',case_link:'existing',source_segment_ids:[]}],
  claims:[claim,unsupported],
}
const wire=(id:string,value:unknown)=>({
  id,status:'completed',output:[{type:'message',role:'assistant',status:'completed',
    content:[{type:'output_text',text:JSON.stringify(value),annotations:[]}]}],
  usage:{input_tokens:1000,output_tokens:100,total_tokens:1100,
    input_tokens_details:{cached_tokens:200,cache_write_tokens:0},output_tokens_details:{reasoning_tokens:40}},
})
const provider:BackgroundProvider={
  async submit(_key,args) {
    const id='resp_'+(calls.length+1)
    calls.push({id,args,at:now})
    return id
  },
  async collect(_key,id) {
    const operation=calls.find(x=>x.id===id)!
    if(now-operation.at<63_000) return {id,status:'in_progress',output:[]}
    if(operation.args.stage==='primary') return wire(id,answer)
    if(operation.args.stage==='repair') return wire(id,{removals:['unsupported'],replacements:[],additions:[]})
    return wire(id,{
      claims:[{claim_id:'supported',support:'supported',reason:'Exact passage applies',requires_public_evidence:true}],
      patch_verdicts:[],primary_question_answered:true,next_action_useful:true,cross_block_coherent:true,repair_instructions:[],
    })
  },
  async cancel(_key,id) { cancelled.push(id) },
}
const sql = async <T>(statement:string,params:unknown[]=[]) => (await db.query<T>(statement,params)).rows
const rpc=async <T>(name:string,args:Record<string,unknown>={}) =>
  (await sql<{value:T}>(`select public.${name}(${Object.keys(args).map((key,j)=>key+'=> $'+(j+1)).join(',')}) value`,Object.values(args)))[0].value
const store=turnWorkStore(rpc)
function freshHandler() {
  return createResumableHandler({
    rpc,provider,key:'fixture',scheduleSecret:'worker',webhookSecret:'',
    async authenticate(token) {return token===owner || token===stranger ? {id:token} : null},
    async read(user,conversation,request) {
      return (await sql<any>('select id execution_id,request_id,status,result,error_detail from nyay_turn_executions where owner_id=$1 and conversation_id=$2 and (($3::text is null and status in (\'queued\',\'running\')) or request_id=$3)',[user,conversation,request || null]))[0] || null
    },
    events:(user,id,seq)=>sql<any>("select * from nyay_turn_events where owner_id=$1 and execution_id=$2 and seq>$3 and publication_status='published' order by seq limit 100",[user,id,seq]),
    retrieve:async()=>({passages:[retiredEvidence,refundEvidence,regionalEvidence],limitations:['Synthetic dataset']}),
    prepare:async()=>({
      memory:{version:0,memory:defaultCaseMemory(),summary:'',staged_patches:[],case_proposals:[],quality_review_consent:false},
      requestId:'fixture-request',region:null,incidentDate:'2025-02-01',asOfDate:'2026-11-20',
      priorMessages:[],attachments:[],urgent:false,
    }),
  },async()=>new Response(null,{status:204}))
}
async function request(path:string,token:string,body?:unknown) {
  return freshHandler()(new Request(base+path,{
    method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token},
    body:body===undefined?undefined:JSON.stringify(body),
  }))
}
const thread=()=>'/api/conversations/'+chat+'/turns'
const payload=(id:string)=>({request_id:id,content:'How can I request a refund?',language:'en',attachment_ids:[]})
const admit=(id:string)=>request(thread(),owner,payload(id))
async function tick(seconds=5) {
  now+=seconds*1000
  // Advance the test scheduler without wall-clock sleeps. The real SQL still owns claiming and fencing.
  await db.exec("update nyay_turn_work set due_at=clock_timestamp() where lease_until is null")
  const wall=performance.now()
  const res=await request('/internal/resumable/sweep','worker',{})
  expect(res.status).toBe(200)
  expect(performance.now()-wall).toBeLessThan(5000)
  return (await res.json()).processed
}
beforeAll(async()=>{
  db=new PGlite()
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as
      $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
    grant usage on schema public,auth to authenticated,anon,service_role;
    insert into auth.users values ('${owner}'),('${stranger}');
  `)
  for(const path of Object.keys(migrations).sort()) await db.exec(migrations[path])
  const [result]=await sql<{id:string}>("insert into nyay_cases(owner_id,incident_date) values($1,'2025-02-01') returning id",[owner])
  const [row]=await sql<{id:string}>("insert into nyay_conversations(owner_id,case_id) values($1,$2) returning id",[owner,result.id])
  chat=row.id
},60_000)
afterAll(async()=>{await db?.close()})

it('reconnects and publishes once after a >200s simulated reviewed turn with targeted repair',async()=>{
  const first=await admit('long')
  expect(first.status).toBe(202)
  const {execution_id}=await first.json()
  expect((await (await admit('long')).json()).execution_id).toBe(execution_id)
  expect((await request(thread(),owner,{...payload('long'),content:'Changed payload'})).status).toBe(409)
  expect((await request(thread()+'/long/events',stranger)).status).toBe(404)
  expect((await request(thread()+'/long/cancel',stranger,{})).status).toBe(404)

  const stale=(await store.claim())!
  expect(await store.claim()).toBeNull()
  await db.exec("update nyay_turn_work set lease_until=clock_timestamp()-interval '1 second'")
  expect(await tick()).toBe(true)
  expect(await store.advance(stale,'failed',{})).toBe(false)

  let final:any
  const initial=await (await request(thread()+'/long/events',owner)).json()
  const cursor=initial.events.at(-1).seq
  for(let step=0;step<65;step++){
    await tick()
    final=await (await request(thread()+'/long/events?after_seq='+cursor,owner)).json()
    if(final.turn.status==='completed') break
    expect(final.events.some((event:any)=>event.kind==='answer_block')).toBe(false)
  }
  expect(final.turn.status).toBe('completed')
  expect(now).toBeGreaterThan(200_000)
  expect(calls.map(c=>c.args.stage)).toEqual(['primary','review','repair','review'])
  expect(final.turn.result.assistant_message.content).toContain('[1](#cite-1)')
  expect(final.turn.result.assistant_message.content).not.toContain('cash penalty')
  expect(final.turn.result.assistant_message.metadata.publication_status).toBe('partial')
  expect(final.turn.result.sources[0].passage_id).toBe(refundEvidence.passageId)
  expect(final.events.filter((e:any)=>e.kind==='result')).toHaveLength(1)
  const seq=final.events.map((event:any)=>event.seq)
  expect(seq).toEqual(Array.from(new Set(seq)).sort((a:any,b:any)=>a-b))
  expect(await tick()).toBe(false)
  expect((await sql("select id from nyay_messages where request_id='long' and role='assistant'"))).toHaveLength(1)
  const metricsResponse=await request(thread()+'/long/metrics',owner)
  expect(metricsResponse.status).toBe(200)
  const metrics=await metricsResponse.json()
  expect(metrics.runtime).toEqual(DEFAULT_RUNTIME)
  const otherRuntime=runtimeConfig({model:'gpt-6.2-astra',reasoning:'high'})
  await rpc('nyay_resume_admit',{p_owner:owner,p_chat:chat,p_request:'long',
    p_payload:{content:payload('long').content,language:'en',attachment_ids:[]},
    p_reserve:runReserve(otherRuntime),p_runtime:otherRuntime})
  expect((await (await request(thread()+'/long/metrics',owner)).json()).runtime).toEqual(DEFAULT_RUNTIME)
  expect(metrics.calls).toHaveLength(4)
  expect(metrics.calls.every((c:any)=>c.usage_confirmed && c.reasoning_tokens===40 && c.cached_tokens===200)).toBe(true)
  expect(Number(metrics.accounted_usd)).toBeCloseTo(4*usageCost(DEFAULT_RUNTIME,wire('',{}).usage),8)
  expect(Number(metrics.accounted_usd)).toBeLessThan(Number(metrics.reserved_usd))
  expect(metrics.steps.some((s:any)=>s.stage==='collect')).toBe(true)
  expect(metrics.steps.some((s:any)=>s.outcome==='waiting')).toBe(true)
  expect(JSON.stringify(metrics)).not.toContain(refundEvidence.text)
  expect(JSON.stringify(metrics)).not.toContain(payload('long').content)
  expect((await request(thread()+'/long/metrics',stranger)).status).toBe(404)
  const [before]=await sql<any>('select estimated_spend_usd from nyay_usage_budgets where owner_id=$1',[owner])
  const [receipt]=await sql<any>('select intent,response_id from nyay_runtime_calls where execution_id=$1 limit 1',[execution_id])
  await rpc('nyay_record_model_response',{p_id:execution_id,p_intent:receipt.intent,p_response:receipt.response_id,p_status:'completed',p_usage:wire('',{}).usage})
  const [after]=await sql<any>('select estimated_spend_usd from nyay_usage_budgets where owner_id=$1',[owner])
  expect(after.estimated_spend_usd).toEqual(before.estimated_spend_usd)
  // The completed first turn no longer consumes the full daily cap.
  expect((await admit('follow-up')).status).toBe(202)
  expect((await request(thread()+'/follow-up/cancel',owner,{})).status).toBe(200)
  await db.exec('set role authenticated')
  await expect(db.query('select checkpoint from nyay_turn_work')).rejects.toThrow('permission denied')
  for(const table of ['nyay_runtime_runs','nyay_runtime_calls','nyay_runtime_steps']) {
    await expect(db.query('select * from '+table)).rejects.toThrow('permission denied')
  }
  await expect(rpc('nyay_run_observability',{p_owner:owner,p_chat:chat,p_request:'long'})).rejects.toThrow('permission denied')
  await db.exec('reset role')
},30_000)

it('fences cancellation and does not resubmit an ambiguous provider intent',async()=>{
  await db.exec('truncate nyay_usage_budgets')
  expect((await admit('cancel')).status).toBe(202)
  await tick()
  await tick()
  await tick()
  const stale=(await store.claim()) // Collect may not be due yet.
  expect((await request(thread()+'/cancel/cancel',owner,{})).status).toBe(200)
  if(stale) expect(await store.advance(stale,'ready',{})).toBe(false)
  await tick()
  expect(cancelled).toContain(calls.at(-1)!.id)
  expect((await (await request(thread()+'/cancel/events',owner)).json()).turn.status).toBe('interrupted')

  await db.exec('truncate nyay_usage_budgets')
  expect((await admit('lost-receipt')).status).toBe(202)
  await tick()
  await tick()
  const claimed=(await store.claim())!
  expect(await store.advance(claimed,'submitting',{...claimed.checkpoint,intent:crypto.randomUUID()},{keepLease:true})).toBe(true)
  const count=calls.length
  await db.exec("update nyay_turn_work set lease_until=clock_timestamp()-interval '1 second'")
  await tick()
  expect(calls).toHaveLength(count)
  const {turn}=await (await request(thread()+'/lost-receipt/events',owner)).json()
  expect(turn.error_detail.code).toBe('submission_unconfirmed')
  const metrics=await (await request(thread()+'/lost-receipt/metrics',owner)).json()
  expect(Number(metrics.accounted_usd)).toBeCloseTo(callReserve(DEFAULT_RUNTIME),8)
  expect(Number(metrics.accounted_usd)).toBeLessThan(runReserve(DEFAULT_RUNTIME))
  expect(metrics.calls[0].usage_confirmed).toBe(false)
})

it('applies date, region, review and linked evidence constraints',()=>{
  const result={passages:[retiredEvidence,refundEvidence,bankingEvidence,regionalEvidence],limitations:[]}
  const request={query:'fixture',region:'Karnataka',incidentDate:'2025-01-01',asOfDate:'2026-11-20',limit:8,signal:new AbortController().signal}
  expect(applicablePassages(result,request)).toEqual([refundEvidence,bankingEvidence,regionalEvidence])
  expect(applicablePassages(result,{...request,region:null})).toEqual([refundEvidence,bankingEvidence])
  expect(applicablePassages(result,{...request,incidentDate:null})).toEqual([])
  expect(applicablePassages({passages:[regionalEvidence],limitations:[]},request)).toEqual([])
})

it('authenticates the exact webhook body and rejects stale deliveries',async()=>{
  const secret=btoa('fixture-signing-secret')
  const raw=JSON.stringify({type:'response.completed',data:{id:'resp_123'}})
  const timestamp='1900000000'
  const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(atob(secret)),{name:'HMAC',hash:'SHA-256'},false,['sign'])
  const signature=await crypto.subtle.sign('HMAC',key,new TextEncoder().encode('evt_fixture.'+timestamp+'.'+raw))
  const signed=(body:string)=>new Request(base,{method:'POST',body,headers:{
    'webhook-id':'evt_fixture','webhook-timestamp':timestamp,
    'webhook-signature':'v1,'+btoa(String.fromCharCode(...new Uint8Array(signature))),
  }})
  const issued=Number(timestamp)*1000
  expect(await verifyCompletionWebhook(signed(raw),'whsec_'+secret,issued)).toEqual({delivery:'evt_fixture',responseId:'resp_123'})
  await expect(verifyCompletionWebhook(signed(raw+' '),'whsec_'+secret,issued)).rejects.toThrow('signature')
  await expect(verifyCompletionWebhook(signed(raw),'whsec_'+secret,issued+301_000)).rejects.toThrow('headers')
})

it('reconciles a lost acknowledgement and deduplicates completion wakes',async()=>{
  await db.exec('truncate nyay_usage_budgets')
  const response=await admit('recover-receipt')
  expect(response.status).toBe(202)
  const {execution_id}=await response.json()
  await tick()
  await tick()
  const lost=(await store.claim())!
  const intent=crypto.randomUUID()
  expect(await store.advance(lost,'submitting',{...lost.checkpoint,intent,submittedAt:now},{keepLease:true})).toBe(true)
  const reconcile=()=>rpc<boolean>('nyay_resume_reconcile',{p_intent:intent,p_response:'resp_recovered'})
  expect(await reconcile()).toBe(false)
  await db.exec("update nyay_turn_work set lease_until=clock_timestamp()-interval '1 second'")
  expect(await reconcile()).toBe(true)
  const wake=()=>rpc<string>('nyay_resume_wake',{p_delivery:'evt_recovery_fixture',p_response:'resp_recovered'})
  expect(await wake()).toBe('woken')
  expect(await wake()).toBe('duplicate')
  const [state]=await sql<{stage:string;checkpoint:{responseId:string}}>('select stage,checkpoint from nyay_turn_work where execution_id=$1',[execution_id])
  expect(state.stage).toBe('collect')
  expect(state.checkpoint.responseId).toBe('resp_recovered')
  expect((await request(thread()+'/recover-receipt/cancel',owner,{})).status).toBe(200)
  await tick()
  expect(cancelled).toContain('resp_recovered')
})

it('enforces the project cap across owners and releases cancellation reservations',async()=>{
  await db.exec('truncate nyay_usage_budgets')
  const requests:Array<{conversation:string;user:string;id:string}>=[]
  for(let i=0;i<5;i++) {
    const user=i%2?owner:stranger
    const [c]=await sql<any>('insert into nyay_cases(owner_id) values($1) returning id',[user])
    const [v]=await sql<any>('insert into nyay_conversations(owner_id,case_id) values($1,$2) returning id',[user,c.id])
    requests.push({conversation:v.id,user,id:'parallel-'+i})
  }
  const admitOne=(r:typeof requests[number])=>request('/api/conversations/'+r.conversation+'/turns',r.user,payload(r.id))
  const admitted=await Promise.all(requests.map(admitOne))
  expect(admitted.map(r=>r.status)).toEqual([202,202,202,429,429])
  const [usage]=await sql<any>('select sum(estimated_spend_usd) total from nyay_usage_budgets')
  expect(Number(usage.total)).toBeCloseTo(runReserve(DEFAULT_RUNTIME)*3,8)
  for(const r of requests.slice(0,3)) {
    expect((await request('/api/conversations/'+r.conversation+'/turns/'+r.id+'/cancel',r.user,{})).status).toBe(200)
  }
  const [settled]=await sql<any>('select sum(estimated_spend_usd) total from nyay_usage_budgets')
  expect(Number(settled.total)).toBe(0)
  expect((await admitOne(requests[4])).status).toBe(202)
  await request('/api/conversations/'+requests[4].conversation+'/turns/'+requests[4].id+'/cancel',requests[4].user,{})
})

it('retains ambiguous costs until a late verified usage receipt settles exactly once',async()=>{
  await db.exec('truncate nyay_usage_budgets')
  const {execution_id}=await (await admit('late-usage')).json()
  await tick();await tick()
  const job=(await store.claim())!
  const intent=crypto.randomUUID()
  expect(await store.advance(job,'submitting',{...job.checkpoint,intent},{keepLease:true})).toBe(true)
  await request(thread()+'/late-usage/cancel',owner,{})
  const before=await (await request(thread()+'/late-usage/metrics',owner)).json()
  expect(Number(before.accounted_usd)).toBeCloseTo(callReserve(DEFAULT_RUNTIME),8)
  const record=()=>rpc('nyay_record_model_response',{p_id:null,p_intent:intent,
    p_response:'resp_late_usage',p_status:'completed',p_usage:wire('',{}).usage})
  await rpc('nyay_record_model_response',{p_id:null,p_intent:intent,p_response:'resp_late_usage',p_status:'completed',
    p_usage:{...wire('',{}).usage,input_tokens_details:{cached_tokens:200}}})
  const partial=await (await request(thread()+'/late-usage/metrics',owner)).json()
  expect(Number(partial.accounted_usd)).toBeCloseTo(0.00302,8)
  expect(partial.calls[0].cache_write_breakdown_known).toBe(false)
  await record();await record()
  const after=await (await request(thread()+'/late-usage/metrics',owner)).json()
  expect(Number(after.accounted_usd)).toBeCloseTo(usageCost(DEFAULT_RUNTIME,wire('',{}).usage),8)
  expect(after.calls).toHaveLength(1)
  await expect(rpc('nyay_record_model_response',{p_id:execution_id,p_intent:intent,
    p_response:'resp_different',p_status:'completed',p_usage:wire('',{}).usage})).rejects.toThrow('mismatch')
  await expect(rpc('nyay_record_model_response',{p_id:execution_id,p_intent:intent,
    p_response:'resp_late_usage',p_status:'completed',p_usage:{input_tokens:1,output_tokens:1,input_tokens_details:{cached_tokens:2}}})).rejects.toThrow('breakdown')
  await tick()
})

it('accounts cache reads, both write lifetimes and reasoning without double charging',async()=>{
  await db.exec('truncate nyay_usage_budgets')
  const {execution_id}=await (await admit('cache-usage')).json()
  await tick();await tick()
  const job=(await store.claim())!
  const intent=crypto.randomUUID()
  const state={...job.checkpoint,intent,responseId:'resp_cache_usage'}
  expect(await store.advance(job,'submitting',state,{keepLease:true})).toBe(true)
  expect(await store.advance(job,'collect',state)).toBe(true)
  const usage={...wire('',{}).usage,input_tokens_details:{cached_tokens:200,cache_write_tokens:300,
    cache_write_tokens_details:{ttl_30m_tokens:200,ttl_12h_tokens:100}}}
  await rpc('nyay_record_model_response',{p_id:execution_id,p_intent:intent,p_response:'resp_cache_usage',p_status:'completed',p_usage:usage})
  await request(thread()+'/cache-usage/cancel',owner,{})
  const metrics=await (await request(thread()+'/cache-usage/metrics',owner)).json()
  expect(Number(metrics.accounted_usd)).toBeCloseTo(usageCost(DEFAULT_RUNTIME,usage),8)
  expect(metrics.calls[0]).toMatchObject({cached_tokens:200,cache_write_tokens:300,
    cache_write_30m_tokens:200,cache_write_12h_tokens:100,reasoning_tokens:40,cache_write_breakdown_known:true})
  await tick()
})
