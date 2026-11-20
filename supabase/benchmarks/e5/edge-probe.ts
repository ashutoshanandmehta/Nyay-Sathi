import * as ort from 'npm:onnxruntime-web@1.31.1/wasm'
import { createHash } from 'node:crypto'
import { probes } from './probes.ts'

const revision = '761b726dd34fb83930e26aab4e9ac3899aa1fa78'
const modelUrl = 'https://huggingface.co/Xenova/multilingual-e5-small/resolve/' + revision + '/onnx/model_quantized.onnx'
const modelDigest = 'f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193'
const modelBytes = 118308185
const authHash = '__AUTH_HASH__'
const expiresAt = 0 /* supplied only at deployment */
ort.env.wasm.numThreads = 1
ort.env.wasm.proxy = false

function report(stage: string, started: number, extra: Record<string, unknown> = {}) {
  const metric = { type:'nyay.e5_probe', stage, elapsed_ms: Math.round(performance.now()-started),
    memory: Deno.memoryUsage(), ...extra }
  console.info(JSON.stringify(metric))
  return metric
}

async function fetchArtifact() {
  const response = await fetch(modelUrl,{signal:AbortSignal.timeout(18_000)})
  if(!response.ok || !response.body) throw new Error('Artifact download failed: '+response.status)
  const hash=createHash('sha256')
  const artifact=new Uint8Array(modelBytes)
  let cursor=0
  for await (const chunk of response.body) {
    if(cursor+chunk.length>modelBytes) throw new Error('Artifact length mismatch')
    artifact.set(chunk,cursor)
    cursor+=chunk.length
    hash.update(chunk)
  }
  if(cursor!==modelBytes || hash.digest('hex')!==modelDigest) throw new Error('Artifact digest mismatch')
  return artifact
}

export async function probe(readArtifact=fetchArtifact, onVector?:(language:string, vector:number[])=>void) {
  const started=performance.now()
  const baseline=report('baseline',started)
  let stage='artifact'
  try {
    const bytes=await readArtifact()
    const artifact=report('artifact',started,{bytes:bytes.byteLength})
    stage='wasm_session'
    const session=await ort.InferenceSession.create(bytes,{executionProviders:['wasm']})
    const loaded=report('wasm_session',started)
    stage='inference'
    const measurements=[]
    for (const sample of probes) {
      const at=performance.now()
      const ids=BigInt64Array.from(sample.ids.map(x=>BigInt(x)))
      const shape=[1,ids.length]
      const output=await session.run({
        input_ids:new ort.Tensor('int64',ids,shape),
        attention_mask:new ort.Tensor('int64',new BigInt64Array(ids.length).fill(1n),shape),
        token_type_ids:new ort.Tensor('int64',new BigInt64Array(ids.length),shape),
      })
      const tokens=output[session.outputNames[0]].data as Float32Array
      const v=new Float64Array(384)
      for(let i=0;i<tokens.length;i++) v[i%v.length]+=tokens[i]
      const dot=v.reduce((sum,x,i)=>sum+x*sample.vector[i],0)
      const norm=Math.hypot(...v)*Math.hypot(...sample.vector)
      if(onVector) {
        const length=Math.hypot(...v)
        onVector(sample.language,Array.from(v,x=>x/length))
      }
      measurements.push(report('inference',at,{language:sample.language,tokens:ids.length,cosine:dot/norm}))
    }
    await session.release()
    return {baseline,artifact,loaded,measurements}
  } catch (error) {
    const message=error instanceof Error ? error.message.slice(0,300) : 'unknown'
    return {baseline, failure:report(stage,started,{error:message})}
  }
}

// Hosted benchmark accepts an expiring operator token and fixed public test vectors only.
export async function handler(request:Request) {
  const bearer=request.headers.get('Authorization')?.slice(7) || ''
  if(request.method!=='POST' || Date.now()>expiresAt || bearer.length!==64 ||
      createHash('sha256').update(bearer).digest('hex')!==authHash) {
    return Response.json({detail:'Benchmark unavailable'},{status:404})
  }
  return Response.json(await probe())
}

if(import.meta.main) Deno.serve(handler)
