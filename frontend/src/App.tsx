import { useEffect, useRef, useState } from 'react'
import { ChevronDown, FileText, Lock, Menu, MessageSquareMore, MoreHorizontal, PanelRight, Pencil, Plus, ShieldAlert, ShieldCheck, Swords, Trash2 } from 'lucide-react'
import { api } from './api'
import Composer from './components/Composer'
import { AgentWorkflowPanel, CasePanel, Drawer, KnowledgeBasePanel, Sources } from './components/Drawer'
import MessageView from './components/MessageView'
import PracticePanel from './components/PracticePanel'
import Sidebar from './components/Sidebar'
import type { AgentWorkflow, Conversation, Detail, KnowledgeBase, Language, Message, Source, SafetyMessage, StreamEvent } from './types'

const starters=['My refund has not arrived','A product I bought is defective','My order was never delivered','The seller refuses the promised return']
const welcome:Message={id:'welcome',role:'assistant',status:'complete',created_at:'',metadata:{},content:'Tell me what happened in your own words. I’ll help organise the facts, evidence, and practical next step. You can write in English, Hindi, or Hinglish.'}

export default function App(){
  const [items,setItems]=useState<Conversation[]>([]),[active,setActive]=useState(''),[detail,setDetail]=useState<Detail|null>(null)
  const [sidebar,setSidebar]=useState(false),[panel,setPanel]=useState<'case'|'sources'|'drafts'|'knowledge'|'workflow'|'roleplay'|null>(null),[sources,setSources]=useState<Source[]>([]),[sourceFocus,setSourceFocus]=useState<number|undefined>()
  const [knowledge,setKnowledge]=useState<KnowledgeBase|null>(null),[workflow,setWorkflow]=useState<AgentWorkflow|null>(null)
  const [language,setLanguage]=useState<Language>('en'),[sending,setSending]=useState(false),[error,setError]=useState(''),[menu,setMenu]=useState(false)
  const [configured,setConfigured]=useState(true),pending=useRef<{text:string;id:string;caseId:string;language:Language;attachments:string[]}|null>(null),attachments=useRef<string[]>([]),bottom=useRef<HTMLDivElement>(null)
  const [progress,setProgress]=useState('Saving your message…')
  const [safety,setSafety]=useState<SafetyMessage[]>([])
  const initialized=useRef(false)
  function onProgress(event:StreamEvent){
    if(event.type==='safety'&&event.content_id&&event.text&&event.request_id){
      const item:SafetyMessage={type:'safety',content_id:event.content_id,text:event.text,request_id:event.request_id,sources:event.sources||[]}
      setSafety(previous=>previous.some(x=>x.content_id===item.content_id&&x.request_id===item.request_id)?previous:[...previous,item])
    }else if(event.status==='running'||event.stage==='saving')setProgress(stageLabels[event.stage]||'Preparing your response…')
  }
  const stageLabels:Record<string,string>={saving:'Saving your message…',triage:'Checking what help you need…',intake:'Organising the facts…',research:'Searching saved legal sources…',assess_information:'Checking whether the sources cover your question…',web_research:'Researching the missing information…',web_search:'Searching official websites…',web_fetch:'Reading official pages and documents…',respond:'Preparing your response…',review:'Checking facts and citations…',revise:'Refining the response after review…',verify:'Finalising the checked response…'}
  useEffect(()=>{if(initialized.current)return;initialized.current=true;void initialise()},[]); useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth'})},[detail?.messages,sending])
  stageLabels.plan_resolution='Comparing suitable next steps and preparation…'
  stageLabels.execute_tasks='Working on the parts of your request…'
  stageLabels.web_search='Searching relevant public sources…'
  stageLabels.web_fetch='Reading supporting pages and documents…'
  async function initialise(){try{const boot=await api.bootstrap();setConfigured(boot.ai_configured);const list=await api.list();setItems(list);if(list[0])await select(list[0].id);else await makeNew()}catch(e){setError((e as Error).message)}}
  async function refresh(){const list=await api.list();setItems(list)}
  async function makeNew(){try{const c=await api.create(language);await refresh();await select(c.id);setSidebar(false)}catch(e){setError((e as Error).message)}}
  async function select(id:string){try{const d=await api.detail(id);attachments.current=[];setSafety(d.safety_messages||[]);setActive(id);setDetail(d);setLanguage(d.conversation.language);setSidebar(false);history.replaceState({},'',`/chat/${id}`)}catch(e){setError((e as Error).message)}}
  async function send(text:string){
    if(!active||sending)return false
    const cid=active, req=crypto.randomUUID(), files=[...attachments.current]
    setSending(true);setProgress('Saving your message…');setError('')
    pending.current={text,id:req,caseId:cid,language,attachments:files}
    const optimistic:Message={id:req,role:'user',content:text,status:'sending',created_at:new Date().toISOString(),metadata:{attachment_ids:files}}
    setDetail(d=>d?{...d,messages:[...d.messages,optimistic]}:d)
    try{
      await api.streamTurn(cid,text,language,req,files,onProgress)
      pending.current=null;attachments.current=[]
      const result=await api.detail(cid);setDetail(d=>d?.conversation.id===cid?result:d)
      await refresh();return true
    }catch(e){setError((e as Error).message);setDetail(d=>d?{...d,messages:d.messages.map(m=>m.id===req?{...m,status:'failed'}:m)}:d);return false}
    finally{setSending(false)}
  }
  async function remove(){if(!active||!confirm('Delete this chat, its evidence, drafts, and saved graph state? This cannot be undone.'))return;await api.remove(active);setDetail(null);setActive('');await refresh();await makeNew()}
  async function rename(){if(!active||!detail)return;const title=prompt('Rename this chat',detail.conversation.title)?.trim();if(!title)return;await api.rename(active,title);await select(active);await refresh();setMenu(false)}
  async function showKnowledge(){setPanel('knowledge');setSidebar(false);try{setKnowledge(await api.knowledgeBase())}catch(e){setError((e as Error).message)}}
  async function showWorkflow(){setPanel('workflow');setSidebar(false);try{setWorkflow(await api.agentWorkflow())}catch(e){setError((e as Error).message)}}
  async function retry(){const p=pending.current;if(!p||p.caseId!==active||sending)return;setSending(true);setError('');try{await api.streamTurn(p.caseId,p.text,p.language,p.id,p.attachments,onProgress);const result=await api.detail(p.caseId);setDetail(d=>d?.conversation.id===p.caseId?result:d);pending.current=null;await refresh()}catch(e){setError((e as Error).message)}finally{setSending(false)}}
  async function speech(m:Message){const response=await fetch(`/api/conversations/${active}/messages/${m.id}/speech`,{method:'POST',credentials:'include',headers:{'X-CSRF-Token':decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('nyay_csrf='))?.split('=')[1]||'')}});if(!response.ok){setError('Audio could not be created. The text answer is still available.');return}new Audio(URL.createObjectURL(await response.blob())).play()}
  const messages=detail?.messages.length?detail.messages:[welcome]
  const hasSufficientContext = Boolean(
    detail &&
    detail.messages.some(m => m.role === 'assistant' && m.status === 'complete') &&
    (Object.keys(detail.case_memory?.facts || {}).length > 0 || detail.messages.length >= 2)
  )
  return <div className="app-shell">
    <Sidebar open={sidebar} items={items} active={active} onNew={makeNew} onSelect={select} onClose={()=>setSidebar(false)} onKnowledge={showKnowledge} onWorkflow={showWorkflow}/>{sidebar&&<div className="scrim" onClick={()=>setSidebar(false)}/>}
    <main className="chat-shell">
      <header className="topbar"><button className="menu-button" onClick={()=>setSidebar(true)} aria-label="Open chat history"><Menu/></button><button className="mobile-new" onClick={makeNew} aria-label="New chat"><Plus/></button><div className="case-title"><b>{detail?.conversation.title||'Nyay Saathi'}</b><span>{configured?'AI legal information assistant':'AI setup required'}</span></div><div className="top-actions"><select aria-label="Response language" value={language} onChange={e=>setLanguage(e.target.value as Language)}><option value="en">English</option><option value="hi">हिन्दी</option><option value="hinglish">Hinglish</option></select>{hasSufficientContext?<button onClick={()=>setPanel('roleplay')} className="topbar-roleplay-btn unlocked" title="Practice roleplay with opposing stakeholders"><Swords size={16}/> Roleplay</button>:<button disabled className="topbar-roleplay-btn locked" title="Describe your situation first to unlock Roleplay"><Lock size={15}/> Roleplay</button>}<button onClick={()=>setPanel('case')}><PanelRight size={17}/> Your case</button><div className="menu-wrap"><button aria-label="Case menu" onClick={()=>setMenu(!menu)}><MoreHorizontal/></button>{menu&&<div className="dropdown"><button onClick={rename}><Pencil/> Rename chat</button><a href={`/api/conversations/${active}/export/docx`}><FileText/> Export DOCX</a><a href={`/api/conversations/${active}/export/pdf`}><FileText/> Export PDF</a><a href={`/api/conversations/${active}/export/json`}><FileText/> Export JSON</a><button className="danger" onClick={remove}><Trash2/> Delete chat</button></div>}</div></div></header>
      {!configured&&<div className="config-banner"><ShieldCheck size={17}/><span>OpenAI is not configured. Your chats and case organisation work, but live AI answers and voice need the backend API key.</span></div>}
      <section className="messages" aria-live="polite"><div className="message-column">
        {messages.map(m=><MessageView key={m.id} message={m} onSources={(s,focus)=>{setSources(s);setSourceFocus(focus);setPanel('sources')}} onRetry={m.status==='failed'?retry:undefined} onSpeech={m.role==='assistant'?()=>speech(m):undefined} onOpenCase={()=>setPanel('case')}/>)}
        {safety.filter(item=>!messages.some(m=>m.metadata?.safety_messages?.some(s=>s.request_id===item.request_id&&s.content_id===item.content_id))).map(item=>(
          <div className="safety-alert-card" role="alert" key={`${item.request_id}:${item.content_id}`}>
            <div className="safety-banner">
              <ShieldAlert size={16} aria-hidden />
              <div>
                <strong>Immediate Protective Advisory</strong>
                <p>{item.text}</p>
              </div>
            </div>
          </div>
        ))}
        {messages.length===1&&messages[0].id==='welcome'&&<div className="starters">{starters.map(s=><button key={s} onClick={()=>send(s)}><span>{s}</span><ChevronDown size={15}/></button>)}</div>}
        {sending&&<div className="thinking" role="status"><i/><i/><i/><span>{progress}</span></div>}{error&&<div className="inline-error" role="alert">{error}</div>}<div ref={bottom}/>
      </div></section>
      <Composer key={active} disabled={sending||!active} onSend={send} onUpload={(id)=>attachments.current.push(id)} onRemove={id=>{attachments.current=attachments.current.filter(x=>x!==id)}}/>
    </main>
    {panel&&<Drawer title={panel==='case'?'Your case':panel==='sources'?'Sources':panel==='knowledge'?'Knowledge Base':panel==='workflow'?'Agent Workflow':panel==='roleplay'?'Roleplay':'Drafts'} onClose={()=>setPanel(null)}>{panel==='roleplay'&&detail?<PracticePanel caseId={active} language={language} onClose={()=>setPanel(null)}/>:panel==='case'&&detail?<CasePanel detail={detail} onRefresh={()=>{if(active)void select(active)}} onImported={cid=>{void refresh().then(()=>select(cid))}}/>:panel==='sources'?<Sources sources={sources} focus={sourceFocus}/>:panel==='knowledge'?(knowledge?<KnowledgeBasePanel data={knowledge}/>:<div className="panel-content"><p>Loading indexed legal sources…</p></div>):panel==='workflow'?(workflow?<AgentWorkflowPanel data={workflow}/>:<div className="panel-content"><p>Loading workflow definition…</p></div>):<div className="panel-content">{detail?.drafts.map(d=><section className="draft" key={d.id}><h3>{d.title}</h3><small>{d.status} · version {d.version}</small><textarea defaultValue={d.content}/></section>)}{!detail?.drafts.length&&<p>No drafts yet. Ask me to draft a factual seller email or complaint.</p>}</div>}</Drawer>}
  </div>
}
