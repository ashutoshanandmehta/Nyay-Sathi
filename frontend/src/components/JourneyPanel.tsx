import { useState } from 'react'
import type { Journey, RouteOption } from '../resolution'
const outcomeLabels:Record<string,string>={unknown:'Outcome not established',promised_pending:'Remedy promised — receipt not established',processed_not_credit_verified:'Refund reported processed — credit not established',remedy_reported_received:'Remedy received, according to your account',unresolved_rejected:'Requested remedy rejected',closed_by_recipient_outcome_unknown:'Ticket closed — outcome not established',partially_resolved:'Partial remedy reported',settlement_reported_accepted:'Settlement accepted, according to your account',pursuit_stopped:'You chose to stop pursuing this'}
const label=(s:string)=>s.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())
function Option({route,primary}:{route:RouteOption;primary:boolean}){
  return <article className={`route-card ${primary?'recommended':''}`}>
    <small>{primary?'Suggested next preparation':'Alternative'} · {label(route.channel)}</small>
    <h4>{route.title}</h4><p>{route.reason}</p>
    {route.eligibility.status==='insufficient_information'&&<p className="route-caveat">Filing eligibility needs checking. You can prepare the facts now.</p>}
    <div className="route-metrics"><span>Preparation effort <b>{label(route.tradeoff.effort)}</b></span><span>Filing fee <b>{route.tradeoff.filing_fee_inr===null?'Not established':`₹${route.tradeoff.filing_fee_inr}`}</b></span></div>
    <details><summary>What to prepare and consider</summary>
      <p>{route.tradeoff.fee_basis}</p><p className="muted">{route.tradeoff.effort_basis}. {route.tradeoff.waiting_time}.</p>
      <ul>{route.preparation.map(item=><li key={item}>{item}</li>)}</ul>
      {route.instructions.map(item=><p key={item}>{item}</p>)}
      {!!route.eligibility.missing_inputs.length&&<><b>Before filing, establish</b><ul>{route.eligibility.missing_inputs.map(item=><li key={item}>{item}</li>)}</ul></>}
      {route.tradeoff.other_costs.map(item=><p key={item}>{item}</p>)}{route.tradeoff.uncertainty.map(item=><p className="muted" key={item}>{item}</p>)}
      {route.source_urls.map((url,i)=><a key={url} href={url} target="_blank" rel="noreferrer">Check official instructions {i+1} ↗</a>)}
    </details>
  </article>
}
export default function JourneyPanel({journey,caseVersion}:{journey:Journey;caseVersion:number}){
  const [all,setAll]=useState(false)
  const current=journey.recommendations?.at(-1)
  const stale=current?.stale||current?.case_version!==caseVersion
  const eligible=current?.alternatives.filter(route=>route.eligibility.status!=='ineligible')||[]
  const superseded=new Set(journey.events.map(event=>event.supersedes_id).filter(Boolean))
  return <section className="journey-panel" aria-label="Complaint journey">
    <div className="journey-status"><b>{outcomeLabels[journey.outcome]||'Outcome needs review'}</b><small>{journey.satisfaction==='accepted'?'You accepted the outcome':journey.satisfaction==='dissatisfied'?'You reported that you are not satisfied':'Your satisfaction has not been established'}</small>{journey.severity!=='ordinary'&&<strong>Priority: {label(journey.severity)} review</strong>}</div>
    {!!journey.events.length&&<details className="case-section" open><summary>Complaint journey <small>{journey.events.length}</small></summary>{journey.events.filter(e=>!superseded.has(e.id)).map(event=><div className="timeline-event" key={event.id}><small>{event.occurred_at||'Event date not established'} · {event.evidence_status==='documentary_statement'?'From a document':'You reported'}</small><p>{event.description}</p>{event.reference&&<small>Reference: {event.reference}</small>}</div>)}</details>}
    {!!journey.commitments.length&&<details className="case-section"><summary>Recorded commitments</summary>{journey.commitments.map(item=><p key={item.event_id}>{item.description}<br/><small>{item.due_at?`Reported target: ${item.due_at}`:'Target date not established'} · {label(item.status)}. This is not a statutory deadline.</small></p>)}</details>}
    {current&&<div className="next-preparation"><h3>Possible next steps</h3>{stale?<p className="route-caveat">The case has changed. Ask for an updated recommendation before using these details.</p>:<>
      {!current.recommended_route_id&&<p className="route-caveat">A detail or your preferred outcome needs review before recommending further action.</p>}
      {(all?eligible:eligible.slice(0,2)).map(route=><Option key={route.route_id} route={route} primary={route.route_id===current.recommended_route_id}/>)}
      {eligible.length>2&&<button className="text-action" onClick={()=>setAll(!all)}>{all?'Show fewer options':'Compare other preparation routes'}</button>}
      {!!current.important_uncertainties.length&&<details><summary>What could change this recommendation?</summary>{current.important_uncertainties.map(item=><p key={item}>{item}</p>)}</details>}
    </>}<small className="muted">Preparation guidance only. Nothing has been submitted; you choose whether to proceed, wait, settle or stop.</small></div>}
  </section>
}
