// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest'
import { LEGAL_CORPUS_BUNDLE } from '../../supabase/functions/nyay-api/legal-corpus-data'
import { createOpenAiQueryEmbedder } from '../../supabase/functions/nyay-api/semantic-retrieval'

afterEach(()=>vi.unstubAllGlobals())

it('sends the version canary with every legal query',async()=>{
  const vector=Array(384).fill(0); vector[0]=1
  vi.stubGlobal('fetch',vi.fn(async(_url:string,init:RequestInit)=>{
    expect(JSON.parse(String(init.body))).toMatchObject({
      model:'text-embedding-3-small',dimensions:384,
      input:[LEGAL_CORPUS_BUNDLE.manifest.embedding_canary.input,'हिंदी query'],
    })
    return Response.json({model:'text-embedding-3-small',data:[
      {index:0,embedding:LEGAL_CORPUS_BUNDLE.manifest.embedding_canary.embedding},
      {index:1,embedding:vector},
    ]})
  }))
  expect(await createOpenAiQueryEmbedder('fixture')('हिंदी query',new AbortController().signal)).toHaveLength(384)
})

it('rejects provider model drift before retrieval',async()=>{
  const drifted=Array(384).fill(0); drifted[0]=1
  vi.stubGlobal('fetch',vi.fn(async()=>Response.json({model:'text-embedding-3-small',data:[
    {index:0,embedding:drifted},{index:1,embedding:drifted},
  ]})))
  await expect(createOpenAiQueryEmbedder('fixture')('query',new AbortController().signal)).rejects.toThrow('drift')
})
