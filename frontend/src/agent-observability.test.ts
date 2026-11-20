// @vitest-environment node
import {afterEach,expect,it,vi} from 'vitest'
import {DEFAULT_RUNTIME,callReserve,runReserve,runtimeConfig,usageCost} from '../../supabase/functions/nyay-api/runtime-config'
import {operationalLog} from '../../supabase/functions/nyay-api/observability'
import {OpenAiBackgroundProvider} from '../../supabase/functions/nyay-api/background-provider'
afterEach(()=>vi.restoreAllMocks())
it('uses validated Sol Medium defaults and estimates bounded Standard-priced work',()=>{
  expect(DEFAULT_RUNTIME).toEqual({model:'gpt-6.2-sol',reasoning:'medium',maxOutputTokens:4096})
  expect(runReserve(DEFAULT_RUNTIME)).toBeCloseTo(1.32864,9)
  const astra=runtimeConfig({model:'gpt-6.2-astra'})
  expect(callReserve(astra)).toBeCloseTo(4*callReserve(DEFAULT_RUNTIME),9)
  for(const options of [{model:'anything'},{reasoning:'none'},{maxOutputTokens:0},{maxOutputTokens:100000}]) {
    expect(()=>runtimeConfig(options)).toThrow('configuration')
  }
  const usage={input_tokens:1000,output_tokens:100,total_tokens:1100,
    input_tokens_details:{cached_tokens:200,cache_write_tokens:0},output_tokens_details:{reasoning_tokens:40}}
  expect(usageCost(DEFAULT_RUNTIME,usage)).toBeCloseTo(0.00262,9)
  expect(usageCost(DEFAULT_RUNTIME,{...usage,input_tokens_details:{cached_tokens:200}})).toBeCloseTo(0.00302,9)
  expect(usageCost(DEFAULT_RUNTIME,{...usage,input_tokens_details:{cached_tokens:200,cache_write_tokens:300,
    cache_write_tokens_details:{ttl_30m_tokens:200,ttl_12h_tokens:100}}})).toBeCloseTo(0.00302,9)
  expect(()=>usageCost(DEFAULT_RUNTIME,{...usage,output_tokens:-1})).toThrow('usage')
})
it('emits whitelisted metrics without arbitrary prompt, token or error content',()=>{
  const log=vi.spyOn(console,'info').mockImplementation(()=>undefined)
  operationalLog('test-run',{stage:'collect',attempt:2,durationMs:12,outcome:'retry',
    prompt:'PRIVATE CASE',apiKey:'secret',error:'provider echoed PRIVATE CASE'} as any)
  const event=JSON.parse(log.mock.calls[0][0])
  expect(event).toMatchObject({type:'nyay.agent.step',stage:'collect',attempt:2,duration_ms:12,outcome:'retry'})
  expect(JSON.stringify(event)).not.toMatch(/PRIVATE|secret|prompt|apiKey/)
})
it('rejects oversized serialized provider requests before a network call',async()=>{
  const fetch=vi.spyOn(globalThis,'fetch').mockRejectedValue(new Error('Must not call'))
  await expect(new OpenAiBackgroundProvider().submit('fixture',{stage:'primary',
    input:[{role:'user',content:'x'.repeat(65000)}]},'fixture')).rejects.toThrow('too large')
  expect(fetch).not.toHaveBeenCalled()
})
