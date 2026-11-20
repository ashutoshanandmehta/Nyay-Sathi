import type { BackgroundProvider } from './background-provider.ts'
import { verifyCompletionWebhook } from './provider-webhook.ts'
import { readBoundedJson } from './bounded-body.ts'
import { runOneTurnStep, type TurnInput, type TurnWork, type TurnWorkStore, type PreparedContext } from './resumable-turn.ts'
import type { RetrieveEvidence } from './retrieval-port.ts'
import { DEFAULT_RUNTIME, runReserve, runtimeConfig, type RuntimeConfig } from './runtime-config.ts'
import { operationalLog } from './observability.ts'

type Rpc = <T>(name:string,args?:Record<string,unknown>)=>Promise<T>
interface VisibleTurn {execution_id:string; status:string; result?:unknown; error_detail?:unknown}
interface EventRow {seq:number; kind:string; payload:Record<string,unknown>; execution_id:string; request_id:string; block_id?:string}
interface Dependencies {
  rpc:Rpc
  authenticate:(token:string|null)=>Promise<{id:string}|null>
  read:(owner:string,chat:string,requestId?:string)=>Promise<VisibleTurn|null>
  events:(owner:string,executionId:string,after:number)=>Promise<EventRow[]>
  prepare:(job:TurnWork)=>Promise<PreparedContext>
  retrieve:RetrieveEvidence
  provider:BackgroundProvider
  key:string
  admissionsPaused?:boolean
  scheduleSecret:string
  webhookSecret:string
  runtime?:RuntimeConfig
}
const uuid=/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i
const requestId=/^[A-Za-z0-9_-]{1,100}$/

export function turnWorkStore(rpc:Rpc):TurnWorkStore {
  return {
    claim:()=>rpc<TurnWork|null>('nyay_resume_claim'),
    advance:(job,stage,state,options)=>rpc<boolean>('nyay_resume_advance',{
      p_id:job.execution_id,p_token:job.lease_token,p_stage:stage,p_state:state,
      p_delay:options?.delay || 0,p_event:options?.event || null,p_keep_lease:options?.keepLease || false,
    }),
    recordResponse:async(job,response)=>{
      await rpc('nyay_record_model_response',{p_id:job.execution_id,p_intent:job.checkpoint.intent,
        p_response:response.id,p_status:response.status,p_usage:response.usage || null})
    },
    observe:async(job,event)=>{
      operationalLog(job.execution_id,event)
      try {
        await rpc('nyay_record_step',{p_id:job.execution_id,p_lease:job.lease_token,p_stage:event.stage,
          p_attempt:event.attempt,p_duration:Math.round(event.durationMs),p_outcome:event.outcome,
          p_evidence:event.evidenceCount || 0,p_blocked:event.blockedClaims || 0})
      } catch {
        console.warn(JSON.stringify({type:'nyay.agent.telemetry_unavailable',execution_id:job.execution_id}))
      }
    },
  }
}

export function createResumableHandler(deps:Dependencies, fallback:(req:Request)=>Promise<Response>) {
  const runtime=runtimeConfig(deps.runtime || DEFAULT_RUNTIME)
  return async (request:Request):Promise<Response> => {
    const url=new URL(request.url)
    let path=url.pathname
    if (path.startsWith('/functions/v1/nyay-api')) {
      path = path.slice('/functions/v1/nyay-api'.length) || '/'
    }
    if (path.startsWith('/nyay-api/')) {
      path = path.slice('/nyay-api'.length)
    } else if (path === '/nyay-api') {
      path = '/'
    }
    if (!path.startsWith('/api') && !path.startsWith('/internal')) {
      path = `/api${path.startsWith('/') ? '' : '/'}${path}`
    }
    const route=path.match(/^\/api\/conversations\/([^/]+)\/turns(?:\/(active|stream|([A-Za-z0-9_-]+)(?:\/(events|cancel|metrics))?))?$/)
    if(path==='/api/bootstrap' && request.method==='GET') {
      const response=await fallback(request)
      if(!response.ok) return response
      const current=await response.json()
      return Response.json({...current,ai_configured:Boolean(deps.key && !deps.admissionsPaused)},{
        status:response.status,headers:response.headers,
      })
    }
    if(!route && path!=='/internal/resumable/sweep' && path!=='/internal/resumable/openai') return fallback(request)
    if(request.method==='OPTIONS') return fallback(request)
    const cors=await fallback(new Request(request.url,{method:'OPTIONS',headers:request.headers}))
    const headers=new Headers(cors.headers)
    headers.set('Content-Type','application/json')
    headers.set('Cache-Control','no-store')
    const json=(body:unknown,status=200)=>Response.json(body,{status,headers})
    try {
      if(path==='/internal/resumable/sweep') {
        if(request.method!=='POST' || !deps.scheduleSecret ||
            request.headers.get('Authorization')!=='Bearer '+deps.scheduleSecret) return json({detail:'Not found'},404)
        if(!deps.key) return json({detail:'Worker unavailable'},503)
        const processed=await runOneTurnStep({...deps,store:turnWorkStore(deps.rpc)})
        return json({processed})
      }
      if(path==='/internal/resumable/openai') {
        if(request.method!=='POST' || !deps.webhookSecret) return json({detail:'Not found'},404)
        let event:Awaited<ReturnType<typeof verifyCompletionWebhook>>
        try { event=await verifyCompletionWebhook(request,deps.webhookSecret) }
        catch { return json({detail:'Invalid webhook'},400) }
        if(!event) return json({received:true})
        // Wake known references even when the response could not be retrieved.
        const known=await deps.rpc<string>('nyay_resume_wake',{p_delivery:event.delivery,p_response:event.responseId})
        if(known!=='unknown') return json({received:true})
        // Unknown reference, including a POST that succeeded before its receipt was saved.
        // Only provider-returned metadata can establish the association.
        const response=await deps.provider.collect(deps.key,event.responseId)
        const intent=response.metadata?.nyay_intent || ''
        if(uuid.test(intent)) await deps.rpc('nyay_record_model_response',{
          p_id:null,p_intent:intent,p_response:response.id,p_status:response.status,p_usage:response.usage || null,
        })
        if(uuid.test(intent) && !await deps.rpc<boolean>('nyay_resume_reconcile',{p_intent:intent,p_response:event.responseId})) {
          return json({detail:'Retry webhook'},503)
        }
        await deps.rpc('nyay_resume_record_delivery',{p_delivery:event.delivery})
        return json({received:true})
      }

      const owner=await deps.authenticate(request.headers.get('Authorization')?.match(/^Bearer (.+)$/i)?.[1] || null)
      if(!owner) return json({detail:'Authentication required'},401)
      const [,chat, action, id, operation]=route!
      if(!uuid.test(chat)) return json({detail:'Conversation not found'},404)
      if(request.method==='POST' && (!action || action==='stream')) {
        if(!deps.key || deps.admissionsPaused) return json({detail:'Resumable AI is unavailable'},503)
        const size=Number(request.headers.get('Content-Length') || 0)
        if(size>24_000) return json({detail:'Turn too large'},413)
        const body=await readBoundedJson(request,24_000).catch(()=>null)
        if(!body || typeof body.content!=='string' || !body.content.trim() || body.content.length>6000 ||
            !['en','hi','hinglish'].includes(body.language) || typeof body.request_id!=='string' ||
            !requestId.test(body.request_id) || !Array.isArray(body.attachment_ids) || body.attachment_ids.length>4 ||
            body.attachment_ids.some((x:unknown)=>typeof x!=='string' || !uuid.test(x))) {
          return json({detail:'Invalid turn input'},422)
        }
        const payload:TurnInput={content:body.content.trim(),language:body.language,attachment_ids:[...new Set<string>(body.attachment_ids)].sort()}
        // Freeze model settings and reserve bounded Standard-priced work. Terminal
        // settlement releases unused budget; ambiguous calls retain a per-call reserve.
        const result=await deps.rpc<VisibleTurn & {error?:string}>('nyay_resume_admit',{
          p_owner:owner.id,p_chat:chat,p_request:body.request_id,p_payload:payload,
          p_reserve:runReserve(runtime),p_runtime:runtime,
        })
        if(result.error) return json({detail:result.error},
          result.error==='not_found'?404:result.error==='budget'?429:409)
        const triggerWorker = () => {
          const runWorker = async () => {
            try {
              const store = turnWorkStore(deps.rpc)
              let steps = 0
              while (steps < 20 && await runOneTurnStep({ ...deps, store })) {
                steps++
              }
            } catch (err) {
              console.error('Turn worker error:', err)
            }
          }
          const edgeRuntime = (globalThis as unknown as { EdgeRuntime?: { waitUntil: (p: Promise<unknown>) => void } }).EdgeRuntime
          if (edgeRuntime?.waitUntil) {
            edgeRuntime.waitUntil(runWorker())
          } else {
            runWorker().catch(() => undefined)
          }
        }
        triggerWorker()
        return json(result,202)
      }
      if(request.method==='POST' && operation==='cancel' && requestId.test(id)) {
        return await deps.rpc<boolean>('nyay_resume_cancel',{p_owner:owner.id,p_chat:chat,p_request:id})
          ? json({status:'interrupted'}) : json({detail:'Active turn not found'},404)
      }
      if(request.method==='GET' && (action==='active' || id && requestId.test(id))) {
        const turn=await deps.read(owner.id,chat,action==='active'?undefined:id)
        if(!turn) return action==='active'?json({turn:null}):json({detail:'Turn not found'},404)
        if(operation==='metrics') return json(await deps.rpc('nyay_run_observability',{
          p_owner:owner.id,p_chat:chat,p_request:id,
        }))
        if(operation==='events') {
          const after=Number(url.searchParams.get('after_seq') || 0)
          if(!Number.isSafeInteger(after) || after<0) return json({detail:'Invalid event cursor'},422)
          if (['queued', 'running', 'preparing', 'submitting', 'collect'].includes(turn.status)) {
            await runOneTurnStep({ ...deps, store: turnWorkStore(deps.rpc) }).catch(() => undefined)
          }
          const freshTurn = (await deps.read(owner.id,chat,action==='active'?undefined:id)) || turn
          return json({turn:freshTurn,events:await deps.events(owner.id,freshTurn.execution_id,after)})
        }
        return json({turn})
      }
      return json({detail:'Unsupported turn operation'},405)
    } catch {
      return json({detail:'Turn service temporarily unavailable'},503)
    }
  }
}
