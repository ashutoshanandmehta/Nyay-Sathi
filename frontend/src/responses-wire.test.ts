// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest'
import { OpenAiResponsesProvider } from '../../supabase/functions/nyay-api/openai-provider'
const provider = new OpenAiResponsesProvider()
const answer = {central_question:'Question', risk:'ordinary' as const, case_stage:'intake',next_action:'Check evidence',factual_issues:[],legal_issues:[],tasks:[],claims:[],case_patches:[]}
const review = {claims:[],patch_verdicts:[],primary_question_answered:true,next_action_useful:true,cross_block_coherent:true,repair_instructions:[]}
const repair = {removals:[],replacements:[],additions:[]}
function wire(value: unknown, status='completed') { return {id:'resp_fixture',object:'response',status,output:[{id:'msg_fixture',type:'message',status:'completed',role:'assistant',content:[{type:'output_text',text:JSON.stringify(value),annotations:[]}]}]} }
function respond(value:unknown) { vi.stubGlobal('fetch', vi.fn(async()=>Response.json(value))) }
afterEach(()=>vi.unstubAllGlobals())
it('parses primary from raw HTTP message content, without SDK convenience fields',async()=>{respond(wire(answer));expect(await provider.generatePrimary({apiKey:'fixture',items:[],context:{},round:0})).toMatchObject({kind:'answer',answer})})
it('parses independent review and targeted repair from raw HTTP',async()=>{respond(wire(review));expect((await provider.reviewCandidate({apiKey:'fixture',answer,pendingClaimIds:[],context:{}})).review).toEqual(review);respond(wire(repair));expect((await provider.repairCandidate({apiKey:'fixture',answer,review,acceptedClaimIds:[],blockedClaimIds:{},context:{}})).repaired).toEqual(repair)})
for(const value of [wire({}),wire(answer,'incomplete'),wire(answer,'failed'),{status:'completed',output:[{type:'message',role:'assistant',content:[{type:'refusal',refusal:'Cannot comply'}]}]}, {status:'completed',output:[]}]) {
 it('rejects invalid/refused/incomplete primary, review and repair',async()=>{respond(value);await expect(provider.generatePrimary({apiKey:'fixture',items:[],context:{},round:0})).rejects.toThrow();await expect(provider.reviewCandidate({apiKey:'fixture',answer,pendingClaimIds:[],context:{}})).rejects.toThrow();await expect(provider.repairCandidate({apiKey:'fixture',answer,review,acceptedClaimIds:[],blockedClaimIds:{},context:{}})).rejects.toThrow()})
}
it('validates tool names, arguments and call identifiers',async()=>{respond({status:'completed',output:[{type:'function_call',call_id:'call_1',name:'invent_tool',arguments:'{}'}]});await expect(provider.generatePrimary({apiKey:'fixture',items:[],context:{},round:0})).rejects.toThrow()})

it('uses supported background submission, collection, tool continuation and cancellation wire formats',async()=>{
  const {OpenAiBackgroundProvider}=await import('../../supabase/functions/nyay-api/background-provider')
  const transport=new OpenAiBackgroundProvider()
  const call={type:'function_call',id:'fc_fixture',call_id:'call_fixture',name:'research_legal_issue',
    arguments:JSON.stringify({questions:[{query:'refund',material_gap:'eligibility'}]}),status:'completed'}
  const reasoning={type:'reasoning',id:'rs_fixture',summary:[],encrypted_content:'opaque-fixture'}
  const mock=vi.fn(async (_url:string,options:RequestInit)=>{
    if(options.method==='GET') return Response.json({id:'resp_fixture',status:'completed',output:[reasoning,call]})
    if(_url.endsWith('/cancel')) return Response.json({id:'resp_fixture',status:'cancelled',output:[]})
    return Response.json({id:'resp_fixture',status:'queued',output:[]})
  })
  vi.stubGlobal('fetch',mock)
  const original=[{role:'user',content:'Synthetic test prompt'}]
  const id=await transport.submit('fixture',{stage:'primary',input:original},'intent-1')
  const {parsePrimary}=await import('../../supabase/functions/nyay-api/openai-provider')
  const result=parsePrimary(await transport.collect('fixture',id))
  expect(result.kind).toBe('tool_calls')
  if(result.kind!=='tool_calls') throw new Error('Expected a tool call')
  const continuation=[...original,...result.rawOutput,{type:'function_call_output',call_id:call.call_id,output:'{}'}]
  await transport.submit('fixture',{stage:'primary',input:continuation},'intent-2')
  await transport.cancel('fixture',id)
  expect(mock.mock.calls.map(args=>args[0].split('/v1/responses')[1])).toEqual(['','/resp_fixture','','/resp_fixture/cancel'])
  expect(JSON.parse(String(mock.mock.calls[2][1].body))).toMatchObject({
    model:'gpt-6.2-sol',reasoning:{effort:'medium'},service_tier:'default',max_output_tokens:4096,
    background:true,store:false,input:continuation,metadata:{nyay_intent:'intent-2'},
    include:['reasoning.encrypted_content'],text:{format:{strict:true}},
  })
})
