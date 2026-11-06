import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(()=>vi.unstubAllGlobals())

it('parses split SSE safety frames before the final result',async()=>{
  const encoder=new TextEncoder()
  let release:()=>void=()=>{}
  const wait=new Promise<void>(resolve=>{release=resolve})
  const events:unknown[]=[]
  const stream=new ReadableStream({async start(controller){
    controller.enqueue(encoder.encode('event: safety\ndata: {"type":"safety","content_id":"s1","text":"Approved safety"'))
    controller.enqueue(encoder.encode('}\n\n'))
    await wait
    controller.enqueue(encoder.encode('event: result\ndata: {}\n\n'))
    controller.close()
  }})
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(stream)))
  const pending=api.streamTurn('c','question','en','request',[],event=>events.push(event))
  await vi.waitFor(()=>expect(events).toHaveLength(1))
  expect(events[0]).toMatchObject({type:'safety',text:'Approved safety',request_id:'request'})
  release()
  await pending
})

it('ignores malformed safety payloads and rejects a stream missing its final result',async()=>{
  const text='event: safety\ndata: {"type":"safety","content_id":5,"text":"bad"}\n\n'
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(text)))
  const callback=vi.fn()
  await expect(api.streamTurn('c','q','en','r',[],callback)).rejects.toThrow('Connection interrupted')
  expect(callback).not.toHaveBeenCalled()
})
