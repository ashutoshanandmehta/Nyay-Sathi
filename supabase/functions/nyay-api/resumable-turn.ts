import type { AgentAnswer, AgentReview, CaseMemoryModel, Language, RepairPatch, ResearchRequest } from './contracts.ts'
import type { DatabasePort } from './handler.ts'
import type { EvidencePassage } from './knowledge.ts'
import { applicablePassages, retrievalDateBasis, type RetrievedPassage, type RetrieveEvidence } from './retrieval-port.ts'
import { AGENT_REPAIR_SCHEMA, AGENT_REVIEW_SCHEMA, parsePrimary } from './openai-provider.ts'
import { LegalEmbeddingUnavailable } from './semantic-retrieval.ts'
import { structured } from './responses-wire.ts'
import type { BackgroundProvider, ModelInput } from './background-provider.ts'
import { ProviderHttpError } from './background-provider.ts'
import { DEFAULT_RUNTIME, MAX_SUBMISSIONS, runtimeConfig, type RuntimeConfig } from './runtime-config.ts'
import type { WireResponse } from './responses-wire.ts'
import type { StepObservation } from './observability.ts'
import { buildSafetyEvent, classifyUrgentContext, detectIndiaContext } from './safety.ts'
import { applyReviewVerdicts, assembleResolutionBlocks, authorizeCasePatches, EvidenceRegistry, mechanicalChecks, propagateDependencies } from './verification.ts'

export interface TurnInput {content:string; language:Language; attachment_ids:string[]}
export type TurnMemory = Awaited<ReturnType<DatabasePort['loadCaseMemory']>>
export interface PreparedContext {
  memory: TurnMemory
  requestId: string
  region: string | null
  incidentDate: string | null
  asOfDate: string
  priorMessages: Array<{id:string;content:string}>
  attachments: Array<{id:string;filename:string;extracted_text:string;consent_status:string}>
  urgent: boolean
  safety?: Record<string, unknown>
}
export interface TurnCheckpoint {
  input: TurnInput
  route?: 'fast' | 'verified' | 'research'
  runtime?:RuntimeConfig
  submissionCount?:number
  context?: PreparedContext
  evidence?: RetrievedPassage[]
  limitations?: string[]
  model?: ModelInput
  intent?: string
  responseId?: string
  submittedAt?: number
  answer?: AgentAnswer
  pending?: string[]
  blocked?: Record<string,string>
  repairable?: string[]
  repaired?: boolean
  withheldRequired?: boolean
  collectionErrors?: number
  toolRounds?: number
  toolOutput?: Extract<ReturnType<typeof parsePrimary>,{kind:'tool_calls'}>
  publication?: Record<string,unknown>
}
export interface TurnWork {
  execution_id:string; owner_id:string; stage:string; lease_token:string; attempts:number
  checkpoint:TurnCheckpoint
}
interface AdvanceOptions {delay?:number; event?:Record<string,unknown>; keepLease?:boolean}
export interface TurnWorkStore {
  claim():Promise<TurnWork|null>
  advance(job:TurnWork, stage:string, checkpoint:Record<string,unknown> | TurnCheckpoint, options?:AdvanceOptions):Promise<boolean>
  recordResponse?(job:TurnWork,response:WireResponse):Promise<void>
  observe?(job:TurnWork,event:StepObservation):Promise<void>
}
interface WorkerDependencies {
  store: TurnWorkStore
  provider: BackgroundProvider
  retrieve: RetrieveEvidence
  prepare: (job:TurnWork)=>Promise<PreparedContext>
  key: string
  now?: ()=>number
}

const messageInput = (content:unknown): ModelInput['input'] => [{role:'user',content:JSON.stringify(content)}]
const stageEvent = (stage:string) => ({stage,status:'running'})
const unique = (ids:string[]) => new Set(ids).size===ids.length
function covers(seen:string[], expected:string[]) {
  return unique(seen) && seen.length===expected.length && seen.every(id=>expected.includes(id))
}
function assertAnswer(answer:AgentAnswer) {
  const tasks=answer.tasks.map(t=>t.task_id)
  const ids=[...tasks,...answer.claims.map(c=>c.claim_id),...(answer.case_patches || []).map(p=>p.patch_id)]
  if (!unique(tasks) || !unique(answer.claims.map(c=>c.claim_id)) ||
      !unique((answer.case_patches || []).map(p=>p.patch_id)) ||
      ids.some(id=>!/^[-a-zA-Z0-9_]{1,100}$/.test(id) || id in Object.prototype) ||
      [...answer.claims,...(answer.case_patches || [])].some(x=>!tasks.includes(x.task_id))) {
    throw new Error('Invalid answer identities')
  }
}

function evidenceRegistry(state:TurnCheckpoint) {
  const context=state.context!
  const passages=(state.evidence || []).map((p):EvidencePassage=>({
    passage_id:p.passageId, source_id:p.documentId, title:p.title, locator:p.locator,
    text:p.text, canonical_url:p.officialUrl, retrieved_at:p.acquiredAt,
    limitations:p.limitations.join(' '), origin:'official_pack', jurisdiction:p.region,
    effective_date:p.validFrom, effective_until:p.validUntil, origin_verified:true,
    verification_status:'official_origin_pending_answer_review',
  }))
  return new EvidenceRegistry({
    current_message:state.input.content, prior_user_messages:context.priorMessages,
    memory:context.memory.memory, attachments:context.attachments, passages,
  })
}

function publication(state:TurnCheckpoint, candidate:AgentAnswer, review?:AgentReview) {
  const context=state.context!
  const registry=evidenceRegistry(state)
  const hasReview=Boolean(review)
  const verified=hasReview && review!.cross_block_coherent===true && review!.primary_question_answered && review!.next_action_useful
  // Truthful acceptance: when semantic review was performed and coherent, apply review verdicts.
  // When review was not performed (e.g. routine procedural or fast route),
  // only accept practical precautions, intake questions, and user-confirmed facts that passed mechanical checks.
  // Never accept unreviewed substantive legal claims!
  const accepted: Record<string, string> = verified
    ? propagateDependencies(candidate,applyReviewVerdicts(review!,state.pending || [],candidate,registry))
    : Object.fromEntries(
        candidate.claims
          .filter(c => (c.kind === 'question' || c.kind === 'practical' || c.grounding === 'reported_by_user') && (!state.blocked || !state.blocked[c.claim_id]))
          .map(c => [c.claim_id, c.grounding || 'procedural_approved'])
      )
  const authorization=authorizeCasePatches({
    answer:verified ? candidate : {...candidate,case_patches:[]},
    review:review || {claims:[],patch_verdicts:[],primary_question_answered:true,next_action_useful:true,cross_block_coherent:true,repair_instructions:[]},
    registry,
    currentMemory:context.memory.memory, requestId:context.requestId,
  })
  const assembled=assembleResolutionBlocks({
    answer:candidate, accepted, registry, language:state.input.language,
    safetyMessages:context.safety ? [context.safety] : [], urgentContinuation:context.urgent,
  })
  // Truthful status: only 'supported' if independently verified and no required claims withheld.
  // When unreviewed or partial, truthfully report 'partial'.
  const hasUnreviewedLegalClaims = candidate.claims.some(
    c => (c.kind === 'legal' || c.grounding === 'verified_legal_source') && !(c.claim_id in accepted)
  )
  const status = (assembled.publicationStatus === 'supported' && verified && !state.withheldRequired && !hasUnreviewedLegalClaims)
    ? 'supported'
    : 'partial'
  const verification={
    passed: status === 'supported',
    independent_review_performed: verified,
    approved_claim_count: Object.keys(accepted).length,
  }
  return {
    expected_version:context.memory.version, memory:authorization.updatedMemory,
    expected_region:context.region, expected_incident_date:context.incidentDate,
    used_attachment_ids:context.attachments.map(item=>item.id),
    staged:[...context.memory.staged_patches,...authorization.stagedPatches],
    proposals:[...context.memory.case_proposals,...authorization.caseProposals],
    content:assembled.content,
    metadata:{publication_status:status,sources:assembled.sources,resolution_blocks:assembled.blocks,
      safety_messages:context.safety ? [context.safety] : [],verification,retrieval_limitations:state.limitations,
      evidence_versions:(state.evidence || []).filter(p=>assembled.sources.some(source=>source.passage_id===p.passageId))
        .map(p=>({passage_id:p.passageId,version:p.version,authority:p.authority,acquired_at:p.acquiredAt}))},
    drafts:verified ? assembled.approvedDocuments.filter(d=>candidate.tasks.some(t=>
      t.task_id===d.task_id && t.intent==='draft' && ['new','existing'].includes(t.case_link)))
      .map(d=>({title:d.title,content:d.content,status:'preliminary'})) : [],
    result:{sources:assembled.sources,verification,ai_configured:true},
  }
}

export async function runOneTurnStep(deps:WorkerDependencies):Promise<boolean> {
  const job=await deps.store.claim()
  if (!job) return false
  const state=job.checkpoint
  const started=performance.now()
  let outcome:StepObservation['outcome']='advanced'
  const now=deps.now || Date.now
  const advance=async(stage:string,options?:AdvanceOptions)=>{
    const changed=await deps.store.advance(job,stage,state,options)
    if(!changed) outcome='fenced'
    else if(stage==='failed') outcome='failed'
    else if(stage===job.stage) outcome=outcome==='failed'?'retry':'waiting'
    return changed
  }
  let failureCode='step_failed'
  const submitNext=(model:ModelInput)=> {
    state.model={...model,runtime:runtimeConfig(state.runtime || DEFAULT_RUNTIME)}
    delete state.responseId
    delete state.intent
    delete state.submittedAt
    delete state.collectionErrors
    return advance('submit',{event:stageEvent(model.stage==='primary'?'generate':model.stage)})
  }
  const dateBasis=() => retrievalDateBasis(state.input.content,state.context!.incidentDate)
  const retrieve=async (query:string, limit=6) => {
    const context=state.context!
    const basis=dateBasis()
    if (basis==='incident_date_required') {
      state.limitations=['The incident date is unconfirmed. Ask the user to confirm it before applying time-bound rules.']
      return []
    }
    const request={dateBasis:basis,query:query.slice(0,6000),region:context.region,incidentDate:context.incidentDate,
      asOfDate:context.asOfDate,limit,signal:AbortSignal.timeout(6_000)}
    const result=await deps.retrieve(request)
    state.limitations=[...new Set([...(state.limitations || []),...result.limitations])].slice(0,12)
    return applicablePassages(result,request)
  }
  try {
    if (job.stage==='prepare') {
      state.context=await deps.prepare(job)
      const text = (state.input.content || '').trim().toLowerCase()
      const isBrief = text.length < 35 && !/\d/.test(text)
      const isGreeting = /^(hi|hello|hey|namaste|shukriya|thanks|thank you|ok|theek hai|kya hal hai)\b/i.test(text)
      if (!state.route) {
        state.route = (isBrief && isGreeting) ? 'fast' : 'verified'
      }
      await advance('retrieve',{event:state.context.safety || {stage:'routing',status:'complete',route:state.route}})
    } else if(job.stage==='retrieve') {
      state.evidence=await retrieve(state.input.content)
      await submitNext({stage:'primary',input:messageInput({
        user_message:state.input.content, language:state.input.language, region:state.context!.region,
        incident_date:state.context!.incidentDate, date_basis:dateBasis(),
        law_as_of_date:dateBasis()==='general_current_law' ? state.context!.asOfDate : null, evidence:evidenceRegistry(state).entries,
        limitations:state.limitations,
      })})
    } else if(job.stage==='submit') {
      if (new TextEncoder().encode(JSON.stringify(state.model)).length>48_000) throw new Error('Provider input too large')
      if((state.submissionCount || 0)>=MAX_SUBMISSIONS) throw new Error('Submission budget exhausted')
      state.submissionCount=(state.submissionCount || 0)+1
      state.intent=crypto.randomUUID()
      state.submittedAt=now()
      // Once claimed, the intent is never resubmitted. A crash after the POST is ambiguous.
      if (!await advance('submitting',{keepLease:true})) return true
      failureCode='submission_unconfirmed'
      state.responseId=await deps.provider.submit(deps.key,state.model!,state.intent)
      if (!await advance('collect',{event:stageEvent('waiting_for_model')})) {
        await deps.provider.cancel(deps.key,state.responseId).catch(()=>undefined)
      }
    } else if(job.stage==='submitting') {
      await advance('failed',{event:{code:'submission_unconfirmed',detail:'The provider submission could not be confirmed. Your message is saved.'}})
    } else if(job.stage==='cancel_provider') {
      if (state.responseId) {
        const cancelled=await deps.provider.cancel(deps.key,state.responseId)
        if(cancelled && deps.store.recordResponse) await deps.store.recordResponse(job,cancelled)
      } else if (state.intent && now()-(state.submittedAt || 0)<90_000 && job.attempts<10) {
        await advance('cancel_provider',{delay:10})
        return true
      }
      await advance('discard')
    } else if(job.stage==='collect') {
      if (job.attempts>64 || now()-state.submittedAt!>30*60_000) {
        await deps.provider.cancel(deps.key,state.responseId!).catch(()=>undefined)
        throw new Error('Collection deadline exceeded')
      }
      const response=await deps.provider.collect(deps.key,state.responseId!)
      if(response.status!=='queued' && response.status!=='in_progress' && deps.store.recordResponse) {
        await deps.store.recordResponse(job,response)
      }
      state.collectionErrors=0
      if (response.status==='queued' || response.status==='in_progress') {
        await advance('collect',{delay:Math.min(30, 2**Math.min(job.attempts,5))})
      } else if (state.model!.stage==='primary') {
        const output=parsePrimary(response)
        if(output.kind==='tool_calls') {
          state.toolOutput=output
          state.route='research'
          await advance('tools',{event:stageEvent('research')})
        } else {
          state.answer=output.answer
          if(state.context!.urgent) state.answer.risk='urgent'
          if(state.route==='fast') {
            state.publication=publication(state,state.answer,undefined)
            await advance('ready',{event:stageEvent('publishing')})
          } else {
            await advance('check',{event:stageEvent('verifying')})
          }
        }
      } else if(state.model!.stage==='review') {
        const review=structured<AgentReview>(response,AGENT_REVIEW_SCHEMA.schema)
        const answer=state.answer!
        // Missing coverage handling: leave affected claims unapproved while preserving independently accepted content
        const coveredClaimIds = new Set((review.claims || []).map(c => c.claim_id))
        const missingClaimIds = (state.pending || []).filter(id => !coveredClaimIds.has(id))
        for (const missingId of missingClaimIds) {
          state.blocked = { ...(state.blocked || {}), [missingId]: 'unreviewed_coverage_gap' }
        }
        // Failure handling: Avoid automatic repair-review loop! Retain approved content, withhold unsupported claims.
        state.publication=publication(state,answer,review)
        await advance('ready',{event:stageEvent('publishing')})
      } else {
        // Retained for backwards-compatibility if an older repair job settles
        const repair=structured<RepairPatch>(response,AGENT_REPAIR_SCHEMA.schema)
        const removals=new Set(repair.removals)
        const replacements=new Map((repair.replacements || []).map(c=>[c.claim_id,c]))
        const touched=[...(repair.removals || []),...(repair.replacements || []).map(c=>c.claim_id)]
        if (repair.additions?.length || !unique(touched) || touched.some(id=>!state.repairable!.includes(id))) {
          throw new Error('Repair changes exceed rejected claim scope')
        }
        state.withheldRequired=state.answer!.claims.some(c=>removals.has(c.claim_id) && !c.optional)
        state.answer!.claims=state.answer!.claims.filter(c=>!removals.has(c.claim_id)).map(c=>replacements.get(c.claim_id) || c)
        state.repaired=true
        state.publication=publication(state,state.answer!,undefined)
        await advance('ready',{event:stageEvent('publishing')})
      }
    } else if(job.stage==='tools') {
      const output=state.toolOutput!
      if ((state.toolRounds || 0)>=2 || output.calls.length!==1) throw new Error('Tool round limit exceeded')
      const call=output.calls[0]
      let result:unknown={status:state.context!.safety ? 'delivered' : 'not_eligible'}
      if(call.name==='research_legal_issue') {
        const request=JSON.parse(call.arguments) as ResearchRequest
        const existing=state.evidence || []
        const room=Math.max(0,8-existing.length)
        // Give the retriever the remaining capacity so it returns whole companion sets.
        const found=room ? await retrieve(request.questions.map(q=>q.query).join(' '),room) : []
        const additions=found.filter(p=>!existing.some(e=>e.passageId===p.passageId))
        state.evidence=[...existing,...additions]
        result={status:additions.length ? 'ok' : 'no_additional_support',evidence:additions,limitations:state.limitations}
      }
      state.toolRounds=(state.toolRounds || 0)+1
      const input=[...state.model!.input,...output.rawOutput,
        {type:'function_call_output',call_id:call.call_id,output:JSON.stringify(result)}]
      delete state.toolOutput
      await submitNext({stage:'primary',input})
    } else if(job.stage==='check') {
      const answer=state.answer!
      assertAnswer(answer)
      const {blocked}=mechanicalChecks(answer,evidenceRegistry(state))
      state.blocked=blocked
      state.pending=answer.claims.filter(c=>!Object.hasOwn(blocked,c.claim_id)).map(c=>c.claim_id)

      // Determine if focused semantic review is required:
      // Triggered for newly generated substantive legal rights, limitation deadlines,
      // or consequential legal advice asserted in pending claims.
      const needsSemanticReview = state.pending.some(id => {
        const claim = answer.claims.find(c => c.claim_id === id)
        return claim && (claim.kind === 'legal' || claim.block_type === 'direct_answer' || claim.grounding === 'verified_legal_source')
      })

      if (needsSemanticReview && state.pending.length > 0) {
        await submitNext({stage:'review',input:messageInput({
          answer,pending_claim_ids:state.pending,evidence:evidenceRegistry(state).entries,
          incident_date:state.context!.incidentDate,date_basis:dateBasis(),
          law_as_of_date:dateBasis()==='general_current_law' ? state.context!.asOfDate : null,region:state.context!.region,
        })})
      } else {
        // Routine procedural assistance (NCH guidance, questions, practical steps)
        // publishes directly after mechanical checks without an extra model call.
        state.publication = publication(state, answer, undefined)
        await advance('ready', { event: stageEvent('publishing') })
      }
    } else if(job.stage==='ready') {
      if(!await deps.store.advance(job,'publish',state.publication!)) outcome='fenced'
    } else {
      throw new Error('Unknown turn stage')
    }
  } catch (error) {
    outcome='failed'
    const retryable=!(error instanceof ProviderHttpError) || error.status===429 || error.status>=500
    if(job.stage==='cancel_provider') {
      await advance(job.attempts<4 && retryable ? 'cancel_provider' : 'discard',{delay:10})
    } else if (job.stage==='collect' && retryable && (state.collectionErrors || 0)<3 &&
        (error instanceof ProviderHttpError || error instanceof DOMException || error instanceof TypeError)) {
      state.collectionErrors=(state.collectionErrors || 0)+1
      await advance('collect',{delay:4*state.collectionErrors})
    } else if (['prepare','retrieve','tools'].includes(job.stage) && retryable && job.attempts<4) {
      await advance(job.stage,{delay:4*job.attempts})
    } else if (job.stage==='submit' && failureCode==='submission_unconfirmed') {
      // Leave the intent available briefly for a signed webhook to reconcile it.
      await advance('submitting',{delay:60})
    } else {
      const event=error instanceof LegalEmbeddingUnavailable
        ? {code:'semantic_retrieval_unavailable',detail:'Legal source search is temporarily unavailable. Your message is saved.'}
        : {code:failureCode,detail:'The answer could not be verified. Your message is saved.'}
      await advance('failed',{event})
    }
  } finally {
    if(deps.store.observe) {
      await deps.store.observe(job,{stage:job.stage,attempt:job.attempts,
        durationMs:performance.now()-started,outcome,evidenceCount:state.evidence?.length,
        blockedClaims:state.blocked?Object.keys(state.blocked).length:undefined,
      }).catch(()=>undefined)
    }
  }
  return true
}

export async function prepareSafety(content:string,language:Language,memory:CaseMemoryModel,
  previous:Array<Record<string,unknown>>) {
  const data=memory as unknown as Record<string,unknown>
  const urgent=classifyUrgentContext(content,data,previous)
  return {
    urgent:urgent.direct_urgent || urgent.urgent_continuation,
    safety:urgent.emit_immediate_safety ? {...await buildSafetyEvent({
      language, category:urgent.category, india:detectIndiaContext(content,data),
    })} : undefined,
  }
}
