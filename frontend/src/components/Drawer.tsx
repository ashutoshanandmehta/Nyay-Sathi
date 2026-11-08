import { ArrowDown, CheckCircle2, Database, ExternalLink, GitBranch, Lock, Scale, ShieldCheck, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { AgentWorkflow, Detail, EscalationBundle, KnowledgeBase, Source } from '../types'
import { api } from '../api'
import JourneyPanel from './JourneyPanel'
import DraftEditor from './DraftEditor'

export function Drawer({title,onClose,children,hideHeader=false}:{title:string;onClose:()=>void;children:React.ReactNode;hideHeader?:boolean}){return <div className="panel-backdrop" onMouseDown={e=>{if(e.currentTarget===e.target)onClose()}}><aside className="panel">{!hideHeader&&<header><h2>{title}</h2><button onClick={onClose} aria-label="Close panel"><X/></button></header>}{children}</aside></div>}
// A bare site root means the exact document is not linked; say so instead of implying it opens.
const isSiteRoot=(url:string)=>{try{return new URL(url).pathname.replace(/\/+$/,'')===''}catch{return false}}
export function Sources({sources,focus}:{sources:Source[];focus?:number}){
  const list=useRef<HTMLDivElement>(null)
  useEffect(()=>{if(focus)list.current?.querySelector(`[data-citation="${focus}"]`)?.scrollIntoView?.({block:'start',behavior:'smooth'})},[focus,sources])
  return <div ref={list} className="panel-content source-list">{sources.map(s=><section key={s.passage_id} data-citation={s.citation_number} className={focus&&s.citation_number===focus?'source-focused':undefined}><div className="source-type">{s.origin==='official_pack'?'Official text, quoted exactly · not reviewed by a lawyer':s.source_type==='indian_official'?'Indian official origin · applicability assessed per claim':s.source_type==='foreign_official'?'Foreign official origin · Indian applicability not established':s.origin==='web'?(s.verification_status==='official_origin_pending_answer_review'?'Official origin · applicability needs review':'Public source · authority not verified'):'Saved official source'}</div><h3>{s.citation_number?<span className="citation-badge" aria-label={`Source ${s.citation_number}`}>{s.citation_number}</span>:null}{s.title}</h3><b>{s.locator}</b><blockquote>{s.text}</blockquote><p className="limitation">{s.limitations}</p><small>Retrieved {s.retrieved_at}{s.effective_date?` · Effective ${s.effective_date}`:''}{s.origin==='web'&&!s.effective_date?' · Effective date unknown':''}</small><a href={s.canonical_url} target="_blank" rel="noreferrer">{isSiteRoot(s.canonical_url)?'Website home page (exact document not linked)':'Open source page'} <ExternalLink size={14}/></a></section>)}</div>
}
const readable=(value:unknown)=>typeof value==='string'?value:JSON.stringify(value)
const humanLabel=(value:string)=>value.replaceAll('_',' ').replace(/^./,v=>v.toUpperCase())
const factStatus=(status:string)=>({user_allegation:'You said',user_confirmed:'Confirmed',document_statement:'From a document',assistant_inference:'Needs review'}[status]||humanLabel(status))

function EvidencePreview({attachment,caseId,onRefresh}:{attachment:Detail['attachments'][number];caseId:string;onRefresh?:()=>void}){
  const [text,setText]=useState(attachment.extracted_text),[status,setStatus]=useState(''),[saving,setSaving]=useState(false)
  const [consent,setConsent]=useState<'consented'|'withheld'>(attachment.consent_status||'consented')
  const metadata=JSON.parse(attachment.metadata_json||'{}') as {pages?:{page:number;start:number;end:number}[]}
  async function save(){setSaving(true);try{await api.correctAttachment(caseId,attachment.id,text);setStatus('Correction saved. Dependent drafts need review.');onRefresh?.()}catch{setStatus('Could not save. Your changes remain here.')}finally{setSaving(false)}}
  async function toggleConsent(){
    const next=consent==='consented'?false:true
    try{const res=await api.setAttachmentConsent(caseId,attachment.id,next);setConsent(res.consent_status);onRefresh?.()}catch{setStatus('Could not update attachment consent.')}
  }
  return <details className="evidence-preview"><summary><span>{attachment.filename}</span><small><span>{attachment.extraction_status==='complete'?'Ready':humanLabel(attachment.extraction_status)}</span> · <span>{consent==='consented'?'AI consent granted':'Withheld from AI'}</span>{metadata.pages?.length?` · ${metadata.pages.length} pages`:''}</small></summary>
    <div className="workspace-inline-row">
      <span className="muted">AI access to this file: <b>{consent==='consented'?'Permitted':'Withheld'}</b></span>
      <button type="button" onClick={toggleConsent}>{consent==='consented'?'Withhold from AI':'Allow AI analysis'}</button>
    </div>
    <p className="muted">Document contents are evidence of what is written, not independent proof of every statement.</p>
    {metadata.pages?.map(page=><details key={page.page}><summary>Page {page.page}</summary><pre>{attachment.extracted_text.slice(page.start,page.end)||'No readable text on this page.'}</pre></details>)}
    <label>Review or correct extracted text<textarea aria-label={`Extracted text from ${attachment.filename}`} value={text} onChange={e=>setText(e.target.value)}/></label>
    {!text&&<p>Text could not be read. You can type the relevant details here or upload a clearer copy.</p>}
    <button disabled={saving||text===attachment.extracted_text} onClick={save}>{saving?'Saving…':'Save correction'}</button><p role="status">{status}</p>
  </details>
}

function BundleList({title,items}:{title:string;items:React.ReactNode[]}){
  return items.length?<section><b>{title}</b><ul>{items.map((item,i)=><li key={i}>{item}</li>)}</ul></section>:null
}

function BundleCard({bundle,caseId}:{bundle:EscalationBundle;caseId:string}){
  const [download,setDownload]=useState<{busy?:string;text?:string;error?:boolean}>({})
  async function save(format:'pdf'|'docx'){
    setDownload({busy:format})
    try{setDownload({text:`Downloaded ${await api.downloadEscalationBundle(caseId,format)}. Check your Downloads folder.`})}
    catch(e){setDownload({text:(e as Error).message,error:true})}
  }
  return <div className="bundle-card">
    <b>{bundle.escalation_recommended?'A lawyer should look at this':'Ready for a lawyer consultation'}</b>
    <BundleList title="Reasons for review" items={bundle.escalation_reasons}/>
    {bundle.executive_summary&&<section><b>Summary</b><p>{bundle.executive_summary}</p></section>}
    <BundleList title="Chronology" items={bundle.chronology.map(e=><><span>{e.date}:</span> {e.summary}</>)}/>
    <BundleList title="Facts stated by the client" items={bundle.stated_facts}/>
    <BundleList title="Questions for counsel" items={bundle.questions_for_counsel}/>
    <BundleList title="Facts to be established" items={bundle.facts_to_establish}/>
    <BundleList title="Not yet verified by Nyay Saathi" items={bundle.not_confirmed}/>
    <BundleList title="Sources relied on" items={bundle.source_backed_analysis.verified_sources.map(s=>s.canonical_url?<a href={s.canonical_url} target="_blank" rel="noreferrer">{s.title}{s.locator?` · ${s.locator}`:''}</a>:<>{s.title}{s.locator?` · ${s.locator}`:''}</>)}/>
    <BundleList title="Evidence files" items={bundle.evidence_index.map(e=>e.filename)}/>
    <BundleList title="Drafts" items={bundle.generated_drafts.map(d=>`${d.title} (version ${d.version})`)}/>
    <div className="bundle-downloads">Download for your lawyer:
      <button type="button" disabled={!!download.busy} onClick={()=>void save('pdf')}>{download.busy==='pdf'?'Preparing…':'PDF'}</button>
      <button type="button" disabled={!!download.busy} onClick={()=>void save('docx')}>{download.busy==='docx'?'Preparing…':'Word'}</button>
    </div>
    {download.text&&<small role="status" className={download.error?'bundle-error':'muted'}>{download.text}</small>}
    <small className="muted">{bundle.autonomy_notice}</small>
  </div>
}

export function CasePanel({detail,onRefresh,onImported}:{detail:Detail;onRefresh?:()=>void;onImported?:(cid:string)=>void}){
  const m=detail.case_memory, facts=Object.entries(m.facts)
  const conflicts=m.contradictions.filter(x=>!(x as {resolved?:boolean}).resolved)
  const overview=facts.filter(([k])=>!['issue_type','requested_remedy'].includes(k)).slice(0,3).map(([,v])=>v.value).join(' ')||detail.messages.find(message=>message.role==='user'&&message.content.length>20)?.content.slice(0,500)||'Tell me what happened. Your case will take shape as we chat.'
  const latestAssistant=[...detail.messages].reverse().find(x=>x.role==='assistant'&&x.status==='complete')
  const nextStep=latestAssistant?.metadata?.next_action || latestAssistant?.metadata?.resolution_blocks?.find(b=>b.block_type==='immediate_actions'||b.block_type==='recommended_route')?.content
  const stage=latestAssistant?.metadata?.case_stage || (m.journey?.outcome && m.journey.outcome !== 'unknown' ? m.journey.outcome : 'intake')

  const [actionTitle,setActionTitle]=useState(''),[actionBusy,setActionBusy]=useState(false)
  const [subChannel,setSubChannel]=useState('Grievance Officer / Portal'),[subReceipt,setSubReceipt]=useState(''),[subMsg,setSubMsg]=useState('')
  const [bundle,setBundle]=useState<EscalationBundle|null>(null),[bundleLoading,setBundleLoading]=useState(false)
  const [passphrase,setPassphrase]=useState(''),[transferJson,setTransferJson]=useState(''),[transferMsg,setTransferMsg]=useState('')
  const cid=detail.conversation.id

  const isUrgentOrCriminal =
    m.domain === 'criminal' ||
    stage.toLowerCase().includes('custody') ||
    stage.toLowerCase().includes('bail') ||
    stage.toLowerCase().includes('arrest') ||
    !!(latestAssistant?.metadata?.safety_messages?.length) ||
    !!(m.questions_for_legal_review?.length)

  async function logAction(){
    if(!actionTitle.trim()||actionBusy)return
    setActionBusy(true)
    try{await api.addUserAction(cid,actionTitle.trim(),'completed');setActionTitle('');onRefresh?.()}finally{setActionBusy(false)}
  }
  async function toggleAction(id:string,current:string){
    const next=current==='completed'?'pending':'completed'
    await api.updateUserAction(cid,id,next);onRefresh?.()
  }
  async function recordStep(step:'previewed'|'consented'|'submitted_by_user'|'receipt_captured'){
    try{await api.recordSubmissionStep(cid,subChannel,step,detail.drafts[0]?.id,subReceipt);setSubMsg(`Recorded: ${humanLabel(step)}`);onRefresh?.()}catch(e){setSubMsg((e as Error).message)}
  }
  async function loadBundle(){
    setBundleLoading(true)
    try{setBundle(await api.escalationBundle(cid))}finally{setBundleLoading(false)}
  }
  async function exportPackage(){
    try{const pkg=await api.exportTransfer(cid,passphrase);setTransferJson(JSON.stringify(pkg,null,2));setTransferMsg('Encrypted transfer package created. Save both this JSON and your passphrase.')}catch(e){setTransferMsg((e as Error).message)}
  }
  async function importPackage(){
    try{const parsed=JSON.parse(transferJson) as Record<string,unknown>;const res=await api.importTransfer(parsed,passphrase);setTransferMsg('Case restored on this device.');onImported?.(res.conversation.id)}catch(e){setTransferMsg((e as Error).message)}
  }

  const verifiedFacts=facts.filter(([,f])=>f.status==='user_confirmed'||f.status==='document_statement')
  const reportedFacts=facts.filter(([,f])=>f.status!=='user_confirmed'&&f.status!=='document_statement')

  return <div className="panel-content case-workspace">
    {/* TIER 1: IMMEDIATE PRIORITY & ORIENTATION */}
    <div className="case-version">
      <span>Private case · v{m.version}</span>
      {m.domain && <span className={`case-domain-pill ${m.domain}`}>{humanLabel(m.domain)}</span>}
      <span className="case-stage-label">Stage: {humanLabel(stage)}</span>
    </div>

    {nextStep&&<div className="next-step-banner priority">
      <CheckCircle2 size={16}/>
      <div>
        <b>Recommended next step</b>
        <p>{nextStep}</p>
      </div>
    </div>}

    {!!(conflicts.length||m.unknowns.length)&&<section className="case-attention-section">
      <h3>Needs your attention</h3>
      {conflicts.map((x,i)=><p className="workspace-warning" key={i}>{x.description||readable(x)}</p>)}
      {m.unknowns.map((x,i)=><p key={i}>{x}</p>)}
    </section>}

    {isUrgentOrCriminal && (
      <section className="elevated-bundle-section">
        <div className="elevated-bundle-header">
          <Scale size={16}/>
          <div>
            <b>Lawyer Escalation Summary & Documents</b>
            <small>Ready to share with an advocate or DLSA legal-aid clinic</small>
          </div>
        </div>
        {bundle ? (
          <BundleCard bundle={bundle} caseId={cid}/>
        ) : (
          <button type="button" className="workspace-btn" disabled={bundleLoading} onClick={loadBundle}>
            <Scale size={14}/> {bundleLoading?'Preparing bundle…':'Prepare Lawyer Escalation Bundle'}
          </button>
        )}
      </section>
    )}

    {/* TIER 2: THE GROUND TRUTH (FACTUAL CORE & EVIDENCE) */}
    <section className="case-overview">
      <h3>What happened</h3>
      <p>{overview}</p>
      <span className="muted">Based on your account and supplied documents.</span>
      {m.requested_remedy ? (
        <>
          <h3>What you want</h3>
          <p>{m.requested_remedy}</p>
        </>
      ) : null}
    </section>

    {!!m.events?.length&&<details className="case-section" open>
      <summary>Timeline <small>{m.events.length}</small></summary>
      {m.events.map((item,i)=><div className="timeline-event" key={i}><small>{String(item.date||'Date to check')}</small><p>{String(item.description||'')}</p></div>)}
    </details>}

    <details className="case-section" open>
      <summary>Evidence <small>{detail.attachments.length}</small></summary>
      {detail.attachments.map(a=><EvidencePreview key={a.id} attachment={a} caseId={cid} onRefresh={onRefresh}/>)}
      {!detail.attachments.length&&<p className="muted">Add an invoice, FIR copy, seizure memo, or screenshot using the attachment button.</p>}
    </details>

    {!!facts.length&&<details className="case-section">
      <summary>Important facts <small>{facts.length}</small></summary>
      {!!verifiedFacts.length&&<p className="muted"><b>Confirmed / documentary ({verifiedFacts.length})</b> · Reported / pending check ({reportedFacts.length})</p>}
      {facts.map(([key,fact])=><div className="case-fact" key={key}><span>{humanLabel(key)}</span><p>{fact.value}</p><small className="fact-badge">{factStatus(fact.status)}</small>{!!fact.provenance?.length&&<details><summary>Source details</summary>{fact.provenance.map((p,i)=><p className="muted" key={i}>{p.source_type==='document'?(detail.attachments.find(a=>a.id===p.source_id)?.filename||'Document'):'Your message'}{p.page?` · page ${p.page}`:''}{p.span?` · ${p.span}`:''}</p>)}</details>}</div>)}
    </details>}

    {!!(m.parties?.length||m.locations?.length)&&<details className="case-section">
      <summary>People and places</summary>
      {[...(m.parties||[]),...(m.locations||[])].map((item,i)=><p key={i}>{String(item.name||item.value||'')} <small>{humanLabel(String(item.role||''))}</small></p>)}
    </details>}

    {/* TIER 3: DOMAIN-AWARE ACTION & PREPARATION */}
    <details className="case-section" open>
      <summary>Action tracker <small>{(detail.user_actions?.length||0)+m.actions_completed.length}</small></summary>
      <p className="muted">Record steps you took outside chat so your strategy adjusts automatically.</p>
      <div className="workspace-form-row">
        <input
          aria-label="Record completed action"
          placeholder={m.domain==='criminal'?'e.g. Visited thana, asked for FIR copy, met advocate':'e.g. Sent grievance email with order screenshot'}
          value={actionTitle}
          onChange={e=>setActionTitle(e.target.value)}
        />
        <button type="button" disabled={actionBusy||actionTitle.trim().length<2} onClick={logAction}>Add</button>
      </div>
      {detail.user_actions?.map(act=><div className="action-item" key={act.id}><label><input type="checkbox" checked={act.status==='completed'} onChange={()=>toggleAction(act.id,act.status)}/><span>{act.title}</span></label><small>{humanLabel(act.status)}</small></div>)}
      {m.actions_completed.map((x,i)=><p className="workspace-line" key={i}>{x}</p>)}
      {m.responses_received?.map((x,i)=><p className="workspace-line" key={`r${i}`}>{String(x.description||x.content||'Response recorded')}</p>)}
    </details>

    {!!detail.drafts.length&&<details className="case-section">
      <summary>Drafts <small>{detail.drafts.length}</small></summary>
      {detail.drafts.map(d=><details key={d.id}><summary>{d.title} · {humanLabel(d.status)}</summary><DraftEditor draft={d} caseId={cid}/></details>)}
    </details>}

    {m.domain!=='criminal'&&m.journey&&(m.journey.events.length>0||m.journey.recommendations.length>0)&&(
      <JourneyPanel journey={m.journey} caseVersion={m.version}/>
    )}

    {!isUrgentOrCriminal && (
      <details className="case-section">
        <summary>Lawyer escalation bundle</summary>
        <p className="muted">A summary to share with a lawyer or legal-aid clinic: what happened, your facts, open questions and the sources used. It contains only what you told us and the sources shown.</p>
        <button type="button" className="workspace-btn" disabled={bundleLoading} onClick={loadBundle}><Scale size={14}/> {bundleLoading?'Preparing bundle…':'Prepare Lawyer Escalation Bundle'}</button>
        {bundle&&<BundleCard bundle={bundle} caseId={cid}/>}
        {!!m.questions_for_legal_review?.length&&m.questions_for_legal_review.map((x,i)=><p key={i}>{x}</p>)}
      </details>
    )}

    {/* TIER 4: ADMINISTRATIVE AUDIT & SYSTEM */}
    {!!detail.case_proposals?.length&&<details className="case-section"><summary>Case details awaiting review</summary><p className="muted">These are proposed details. They have not changed your saved case. Correct or restate the details in chat before using them.</p>{detail.case_proposals.map(proposal=><div key={proposal.message_id}>{proposal.base_version!==m.version&&<small className="muted">Earlier proposal — check against your latest case.</small>}{Object.entries(proposal.proposed_facts).filter(([key,fact])=>m.facts[key]?.value!==fact.value).map(([key,fact])=><p key={key}><b>{humanLabel(key)}</b>: {fact.value}</p>)}</div>)}</details>}
    {!!detail.staged_patches?.length&&<details className="case-section"><summary>Details needing clarification <small>{detail.staged_patches.length}</small></summary><p className="muted">These proposals have not changed your saved case. Correct or clarify them in chat.</p>{detail.staged_patches.map(({patch,reason})=><div className="case-fact" key={patch.patch_id}><b>{humanLabel(patch.payload.key||patch.payload.role||'Proposed detail')}</b><p>{patch.payload.value||patch.payload.description||patch.payload.name}</p><small className="muted">{reason}</small></div>)}</details>}

    <details className="case-section">
      <summary>User-confirmed submission tracker <small>{detail.submission_steps?.length||0}</small></summary>
      <p className="muted">Nyay Saathi never files, signs, or pays on your behalf. Confirm each stage yourself and store your acknowledgment reference.</p>
      <div className="workspace-stack">
        <input aria-label="Target forum or channel" value={subChannel} onChange={e=>setSubChannel(e.target.value)} placeholder="Forum / Grievance Officer"/>
        <input aria-label="Submission receipt or ticket reference" value={subReceipt} onChange={e=>setSubReceipt(e.target.value)} placeholder="Docket / NCH / Ticket number (optional)"/>
        <div className="step-buttons">
          <button type="button" onClick={()=>recordStep('previewed')}>1. Previewed</button>
          <button type="button" onClick={()=>recordStep('consented')}>2. Explicit consent</button>
          <button type="button" onClick={()=>recordStep('submitted_by_user')}>3. I submitted</button>
          <button type="button" onClick={()=>recordStep('receipt_captured')}>4. Save receipt</button>
        </div>
        {subMsg&&<small className="muted">{subMsg}</small>}
        {detail.submission_steps?.map(s=><div className="workspace-line" key={s.id}><b>{humanLabel(s.step)}</b> · {s.target_channel}{s.receipt_reference?` · Ref: ${s.receipt_reference}`:''}</div>)}
      </div>
    </details>

    <details className="case-section">
      <summary>Privacy, retention & device transfer</summary>
      <div className="workspace-stack">
        <p className="muted"><Lock size={12}/> Per-case envelope encryption: <b>{detail.encryption?.envelope_encrypted?'Active':'Local'}</b> · Auto-purge after <b>{detail.retention?.days_remaining??365} days</b> of inactivity (delete anytime from Case menu).</p>
        <label className="consent-check">
          <input type="checkbox" checked={!!detail.quality_review_consent?.opted_in} onChange={async e=>{await api.setQualityConsent(cid,e.target.checked);onRefresh?.()}}/>
          <span>Optional: allow de-identified quality review sampling (never used for cross-case training or ad profiling)</span>
        </label>
        <p className="workspace-warning">Guest warning: No phone or email is stored. Losing both this browser credential and your encrypted transfer package permanently loses access.</p>
        <input type="password" aria-label="Transfer passphrase" placeholder="Passphrase (min 8 chars)" value={passphrase} onChange={e=>setPassphrase(e.target.value)}/>
        <div className="step-buttons">
          <button type="button" disabled={passphrase.length<8} onClick={exportPackage}>Export encrypted transfer</button>
          <button type="button" disabled={passphrase.length<8||!transferJson.trim()} onClick={importPackage}>Import transfer JSON</button>
        </div>
        {transferJson&&<textarea aria-label="Encrypted transfer JSON" className="transfer-box" value={transferJson} onChange={e=>setTransferJson(e.target.value)}/>}
        {!transferJson&&<button type="button" className="text-action" onClick={()=>setTransferJson(' ')}>Paste an existing transfer package to import…</button>}
        {transferMsg&&<small className="muted">{transferMsg}</small>}
      </div>
    </details>

    <p className="case-privacy">Private to this browser. Your documents are kept outside the shared legal knowledge base.</p>
  </div>
}

type KnowledgeTab='overview'|'playbooks'|'procedures'|'sources'|'lawyer'
export function KnowledgeBasePanel({data}:{data:KnowledgeBase}){const [tab,setTab]=useState<KnowledgeTab>('overview');return <div className="panel-content knowledge-panel">
  <div className="knowledge-summary"><Database size={20}/><div><b>{data.total_passages} searchable passages</b><span>{data.vector_passages} currently indexed in Chroma · corpus {data.corpus_version}</span></div></div>
  <div className={`index-state ${data.vector_index_enabled?'ready':'limited'}`}><i/>{data.vector_index_enabled?'Vector index connected':'Vector index unavailable; lexical retrieval remains available'}</div>
  <div className="knowledge-tabs" role="tablist">{(['overview','playbooks','procedures','sources','lawyer'] as KnowledgeTab[]).map(item=><button role="tab" aria-selected={tab===item} className={tab===item?'active':''} onClick={()=>setTab(item)} key={item}>{item}</button>)}</div>
  {tab==='overview'&&<>
    <div className="review-state"><b>{data.review_status.replaceAll('_',' ')}</b><span>Version {data.knowledge_version} · checked {data.last_checked}</span></div>
    <p className="knowledge-scope">{data.scope}</p>
    <h3>Knowledge layers</h3><div className="layer-grid">{data.layers.map(layer=><div key={layer.id}><b>{layer.count??'—'}</b><span>{layer.label}</span><small>{layer.storage}</small></div>)}</div>
    <h3>Retrieval pipeline</h3><div className="pipeline-chips">{data.retrieval_pipeline.map(item=><span key={item}>{item}</span>)}</div>
    <h3>Storage boundary</h3><div className="storage-map">{data.storage_map.map(item=><div key={item.store}><b>{item.store}</b><span>{item.content}</span></div>)}</div>
    <p className="knowledge-note">{data.separation_rule}</p>
  </>}
  {tab==='playbooks'&&<>
    <h3>Intake playbooks</h3>{data.intake_playbooks.map(playbook=><details className="knowledge-card" key={playbook.playbook_id}><summary>{playbook.title}</summary><p>Fits: {playbook.applies_to.join(', ').replaceAll('_',' ')}</p><h4>Questions and purpose</h4>{playbook.questions.map(q=><div className="question-row" key={q.field}><b>{q.prompt}</b><span>{q.why}</span></div>)}<h4>Branching checks</h4>{playbook.branches.map(branch=><div className="branch-row" key={branch.if}><b>If {branch.if.replaceAll('_',' ')}</b><span>Ask: {branch.ask.join(', ').replaceAll('_',' ')}</span><small>{branch.reason}</small></div>)}</details>)}
    <h3>Evidence playbooks</h3>{data.evidence_playbooks.map(item=><details className="knowledge-card evidence-card" key={item.evidence_type}><summary>{item.evidence_type.replaceAll('_',' ')}</summary><p>{item.request}</p><div className="evidence-meaning supports"><b>May support</b><span>{item.may_support.join(' · ')}</span></div><div className="evidence-meaning limits"><b>Does not automatically prove</b><span>{item.does_not_automatically_prove.join(' · ')}</span></div><h4>Check</h4><p>{item.authenticity_checks.join(' · ')}</p><h4>Preserve</h4><p>{item.preservation}</p></details>)}
  </>}
  {tab==='procedures'&&<>
    <p className="knowledge-note">Route selection uses explicit inputs, source references, and exceptions. Similarity search alone never selects a forum or deadline.</p>
    {data.procedures.map(route=><details className="knowledge-card" key={route.route_id}><summary>{route.title}</summary><p><b>May fit:</b> {route.when_may_fit}</p><p><b>Authority:</b> {route.authority}</p><h4>Required inputs</h4><ul>{route.required_inputs.map(x=><li key={x}>{x.replaceAll('_',' ')}</li>)}</ul>{route.routing_rules&&<><h4>Explicit routing rules</h4>{route.routing_rules.map(rule=><div className="branch-row" key={rule.rule}><b>{rule.rule.replaceAll('_',' ')}</b><span>Inputs: {rule.inputs.join(', ').replaceAll('_',' ')}</span><small>Exceptions: {rule.exceptions.join(' · ')}</small></div>)}</>}<h4>Prepare and act</h4><ul>{route.instructions.map(x=><li key={x}>{x}</li>)}</ul><p><b>What may follow:</b> {route.what_happens_next}</p><p className="limitation">{route.limitations}</p></details>)}
  </>}
  {tab==='sources'&&<><h3>Official sources and selected passages</h3>
  <div className="knowledge-sources">{data.sources.map(source=><section key={source.source_id}>
    <div className="source-head"><span>{source.source_type.replaceAll('_',' ')}</span><b>{source.verification_status.replaceAll('_',' ')}</b></div>
    <h4>{source.title}</h4><p>{source.issuing_authority} · {source.jurisdiction}</p>
    <div className="source-metrics"><span><b>{source.passage_count}</b> corpus passages</span><span><b>{source.vector_passage_count}</b> vector passages</span></div>
    <details><summary>Indexed locators</summary><ul>{source.locators.map(locator=><li key={locator}>{locator}</li>)}</ul></details>
    <p className="limitation">{source.known_limitations}</p>
    <small>Retrieved {source.retrieved_at}{source.effective_date?` · Effective ${source.effective_date}`:''}</small>
    <a href={source.canonical_url} target="_blank" rel="noreferrer">Open canonical source <ExternalLink size={14}/></a>
  </section>)}</div><h3>Curated judgments</h3>{data.selected_judgments.map(item=><section className="judgment-card" key={item.judgment_id}><b>{item.case_name}</b><span>{item.court} · {item.decision_date} · {item.citation}</span><p>{item.holding_summary}</p><blockquote>“{item.exact_excerpt}” — {item.supporting_locator}</blockquote><p><b>Important distinctions:</b> {item.important_distinctions.join(' · ')}</p><p className="limitation">{item.use_rule} {item.treatment_status}.</p><a href={item.official_url} target="_blank" rel="noreferrer">Open official judgment <ExternalLink size={14}/></a></section>)}</>}
  {tab==='lawyer'&&<>
    <h3>Lawyer briefing pack</h3><ol className="pack-list">{data.lawyer_preparation.pack_sections.map(item=><li key={item}>{item.replaceAll('_',' ')}</li>)}</ol>
    <h3>Consultation questions</h3>{data.lawyer_preparation.consultation_questions.map(item=><p className="workspace-line" key={item}>{item}</p>)}
    <h3>Drafting structures</h3>{data.templates.map(item=><details className="knowledge-card" key={item.template_id}><summary>{item.title}</summary><p><b>Sections:</b> {item.sections.join(' · ').replaceAll('_',' ')}</p><p><b>Confirm first:</b> {item.required_confirmations.join(' · ').replaceAll('_',' ')}</p><p className="limitation"><b>Never invent:</b> {item.must_not_invent.join(' · ')}</p></details>)}
    <h3>Verified referral guidance</h3>{data.referrals.map(item=><section className="referral-card" key={item.referral_id}><b>{item.title}</b><p>{item.provider}</p><p>Services described: {item.services_described.join(' · ')}</p><p className="limitation">Do not promise: {item.do_not_promise.join(' · ')}</p><a href={item.official_url} target="_blank" rel="noreferrer">Open official guidance <ExternalLink size={14}/></a></section>)}
  </>}
</div>}

const arrow=<ArrowDown className="flow-arrow" size={16} aria-hidden/>
function PrimaryWorkflow({data}:{data:AgentWorkflow}){return <div className="panel-content workflow-panel">
  <div className="case-version">{data.version} · live backend definition</div><p className="workflow-intro">Research and review are selected according to the question and available evidence.</p>
  <div className="flow-map">{data.nodes.map((node,index)=><div key={node.id}>{index>0&&arrow}<div className={`flow-node ${node.id==='verify'?'verify':''}`}><GitBranch size={17}/><div><b>{node.label}</b><span>{node.detail}</span></div></div></div>)}</div>
  <h3>Decision rules</h3><div className="decision-list">{data.decisions.map((rule,index)=><div key={index}><b>IF</b><span>{rule.if}</span><strong>THEN</strong><p>{rule.then}</p></div>)}</div>
  <h3>Turn limits</h3><div className="limit-grid"><span><b>{data.limits.model_calls_per_turn}</b> provider requests</span><span><b>{data.limits.retrieval_expansions}</b> research batches</span><span><b>{data.limits.revision_attempts}</b> repair attempt</span></div>
  <details className="edge-details"><summary>Paths and conditions</summary>{data.edges.map((edge,index)=><div key={index}><code>{edge.from} → {edge.to}</code><span>{edge.condition}</span></div>)}</details>
</div>}
export function AgentWorkflowPanel({data}:{data:AgentWorkflow}){if(data.version.startsWith('primary-agent'))return <PrimaryWorkflow data={data}/>;const node=(id:string)=>data.nodes.find(item=>item.id===id)!;const card=(id:string)=><div className={`flow-node ${id==='verify'?'verify':''}`} key={id}>{id==='verify'?<ShieldCheck size={17}/>:id==='research'?<Database size={17}/>:<GitBranch size={17}/>}<div><b>{node(id).label}</b><span>{node(id).detail}</span></div></div>;return <div className="panel-content workflow-panel">
  <div className="case-version">{data.version} · live backend definition</div><p className="workflow-intro">One message follows this route. Branch labels show the actual conditions used to choose the next node.</p>
  <div className="flow-map">{card('checks')}{arrow}{card('context')}{arrow}{card('triage')}{arrow}{card('intake')}{arrow}
    <div className="flow-decision"><div className="decision-label">IF needs_retrieval?</div><div className="decision-branches"><div><span className="branch yes">TRUE</span>{card('research')}{node('assess_information')&&<>{arrow}{card('assess_information')}{arrow}<div className="decision-label">IF public information gap?</div><div className="branch-note">Search only when a public information gap and budget permit. Otherwise continue with local support or clarification.</div>{arrow}{card('web_research')}</>}<ArrowDown className="flow-arrow" size={16}/></div><div><span className="branch no">FALSE</span><div className="branch-note">Skip research</div><ArrowDown className="flow-arrow" size={16}/></div></div></div>
    {node('plan_resolution')&&<>{card('plan_resolution')}{arrow}</>}{node('execute_tasks')&&<>{card('execute_tasks')}{arrow}</>}{card('respond')}{arrow}{card('review')}{arrow}
    <div className="flow-decision"><div className="decision-label">IF review passes?</div><div className="decision-branches"><div><span className="branch yes">PASS</span><div className="branch-note">Continue to hard gate</div><ArrowDown className="flow-arrow" size={16}/></div><div><span className="branch no">REVISE</span>{card('revise')}<ArrowDown className="flow-arrow" size={16}/></div></div></div>
    <p className="muted">Checks apply to each claim independently. A failed lookup does not erase a supported draft. Revision starts only when generation and review both fit the budget.</p>{card('verify')}{arrow}
    <div className="flow-decision"><div className="decision-label">IF verification passes?</div><div className="decision-branches"><div><span className="branch yes">APPROVED CLAIM</span>{card('persist')}</div><div><span className="branch no">AFFECTED CLAIM ONLY</span>{card('withhold')}<ArrowDown className="flow-arrow" size={16}/><div className="mini-persist">Keep supported help; explain unresolved tasks</div></div></div></div>
  </div>
  <h3>Decision rules</h3><div className="decision-list">{data.decisions.map((rule,i)=><div key={i}><b>IF</b><span>{rule.if}</span><strong>THEN</strong><p>{rule.then}</p></div>)}</div>
  <h3>Turn limits</h3><div className="limit-grid"><span><b>{data.limits.model_calls_per_turn}</b> model calls</span><span><b>{data.limits.retrieval_expansions}</b> retrieval expansion</span><span><b>{data.limits.revision_attempts}</b> revision attempt</span></div>
  <details className="edge-details"><summary>All graph edges and conditions</summary>{data.edges.map((edge,i)=><div key={i}><code>{edge.from} → {edge.to}</code><span>{edge.condition}</span></div>)}</details>
</div>}
