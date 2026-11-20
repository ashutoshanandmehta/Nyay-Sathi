import { readBoundedJson } from './bounded-body.ts'
import { LEGAL_CORPUS_BUNDLE } from './legal-corpus-data.ts'
import { createSupabaseLegalRetriever, LEGAL_CORPUS_COVERAGE_DECLARATION, type QueryEmbedder } from './legal-retrieval.ts'
import type { RetrieveEvidence } from './retrieval-port.ts'

const {embeddingModel,embeddingVersion,embeddingDimensions}=LEGAL_CORPUS_COVERAGE_DECLARATION
const embeddingCanary=LEGAL_CORPUS_BUNDLE.manifest.embedding_canary

export function validateQueryVector(vector: unknown): number[] {
  if (!Array.isArray(vector) || vector.length!==embeddingDimensions ||
      vector.some(value=>typeof value!=='number' || !Number.isFinite(value))) {
    throw new Error('Invalid legal query embedding')
  }
  const norm=vector.reduce((sum,value)=>sum+value*value,0)
  if (Math.abs(norm-1)>0.01) throw new Error('Legal query embedding is not normalized')
  return vector
}

export function createVersionedQueryEmbedder(endpoint:string,key:string):QueryEmbedder {
  const url=new URL(endpoint)
  if (url.protocol!=='https:' || url.username || url.password || url.search || url.hash || !key) {
    throw new Error('Invalid legal embedding service configuration')
  }
  return async (query,signal)=>{
    const response=await fetch(url,{
      method:'POST', redirect:'error',
      headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},
      body:JSON.stringify({input:'query: '+query,model:embeddingModel,version:embeddingVersion}),
      signal:AbortSignal.any([signal,AbortSignal.timeout(3000)]),
    })
    if(!response.ok) throw new Error('Legal embedding service unavailable')
    const body=await readBoundedJson(response,32_000)
    if(body?.model!==embeddingModel || body?.version!==embeddingVersion) {
      throw new Error('Legal embedding model mismatch')
    }
    return validateQueryVector(body.embedding)
  }
}

export function createOpenAiQueryEmbedder(apiKey:string):QueryEmbedder {
  if (!apiKey) throw new Error('Invalid OpenAI embedding configuration')
  return async (query,signal)=>{
    const response=await fetch('https://api.openai.com/v1/embeddings',{
      method:'POST', redirect:'error',
      headers:{Authorization:'Bearer '+apiKey,'Content-Type':'application/json'},
      body:JSON.stringify({
        input:[embeddingCanary.input,query],
        model:embeddingModel,
        dimensions:embeddingDimensions,
        encoding_format:'float',
      }),
      signal:AbortSignal.any([signal,AbortSignal.timeout(3_000)]),
    })
    if(!response.ok) throw new Error('OpenAI legal embedding service unavailable')
    const body=await readBoundedJson(response,32_000)
    if(body?.model!==embeddingModel || !Array.isArray(body?.data) || body.data.length!==2 || body.data[0]?.index!==0 || body.data[1]?.index!==1) {
      throw new Error('OpenAI legal embedding response mismatch')
    }
    const canary=validateQueryVector(body.data[0]?.embedding)
    const canaryAgreement=canary.reduce((sum,value,index)=>sum+value*embeddingCanary.embedding[index],0)
    if(canaryAgreement<0.99999) throw new Error('OpenAI legal embedding model drift detected')
    const vector=validateQueryVector(body.data[1]?.embedding)
    const norm=Math.sqrt(vector.reduce((sum,value)=>sum+value*value,0))
    return vector.map(value=>value/norm)
  }
}

export class LegalEmbeddingUnavailable extends Error {}

export function createRequiredSemanticRetriever(
  options:Parameters<typeof createSupabaseLegalRetriever>[0],
):RetrieveEvidence {
  const retrieve=createSupabaseLegalRetriever({...options,embedder:async(query,signal)=>{
    try {
      return validateQueryVector(await options.embedder?.(query,signal))
    } catch {
      // Let the persisted worker retry without treating an outage as a corpus miss.
      throw new LegalEmbeddingUnavailable('Semantic legal retrieval is unavailable')
    }
  }})
  return retrieve
}
