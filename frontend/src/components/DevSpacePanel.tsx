import { Check, Copy, Cpu, Eye, EyeOff, FlaskConical, Gauge, Globe, KeyRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { DevspaceData, DevspaceField, DevspaceSaveResult, DevspaceValue } from '../types'

function getGroupIcon(title: string) {
  const t = title.toLowerCase()
  if (t.includes('model') || t.includes('engine') || t.includes('reasoning')) return Cpu
  if (t.includes('limit') || t.includes('cap') || t.includes('rate') || t.includes('budget') || t.includes('reserve')) return Gauge
  if (t.includes('search') || t.includes('web') || t.includes('retriev') || t.includes('network')) return Globe
  return FlaskConical
}

const PROMPT_LABELS: Record<keyof DevspaceData['prompts'], string> = {
  primary: 'Primary agent (primary.md)',
  review: 'Reviewer (primary-review.md)',
  roleplay_setup: 'Roleplay: stakeholder setup',
  roleplay_persona: 'Roleplay: persona card',
  roleplay_reply: 'Roleplay: in-character reply',
}
const CURL_LABELS: Record<keyof DevspaceData['curl'], string> = {
  turn_stream: 'Stream a chat turn',
  responses_api: 'Direct OpenAI Responses call',
  roleplay_chat: 'Roleplay chat (streamed)',
}

export default function DevSpacePanel({onSaved}:{onSaved?:(result:DevspaceSaveResult)=>void}){
  const [data,setData]=useState<DevspaceData|null>(null),[tab,setTab]=useState<'config'|'prompts'>('config')
  const [edits,setEdits]=useState<Record<string,DevspaceValue>>({}),[custom,setCustom]=useState<Record<string,boolean>>({})
  const [key,setKey]=useState(''),[showKey,setShowKey]=useState(false)
  const [saving,setSaving]=useState(false),[status,setStatus]=useState<{kind:'ok'|'error';text:string}|null>(null),[errors,setErrors]=useState<Record<string,string>>({})
  const [copied,setCopied]=useState('')

  useEffect(()=>{void load()},[])
  async function load(){try{setData(await api.devspace())}catch(e){setStatus({kind:'error',text:(e as Error).message})}}

  const valueOf=(f:DevspaceField)=>f.name in edits?edits[f.name]:f.value
  function change(f:DevspaceField,value:DevspaceValue){
    setEdits(previous=>{const next={...previous};if(value===f.value||(value===''&&f.value===null))delete next[f.name];else next[f.name]=value;return next})
  }

  async function save(clearKey=false){
    const updates:Record<string,DevspaceValue>=clearKey?{}:{...edits}
    if(!clearKey&&key.trim())updates.OPENAI_API_KEY=key.trim()
    if(!clearKey&&!Object.keys(updates).length){setStatus({kind:'ok',text:'Nothing changed.'});return}
    setSaving(true);setStatus(null);setErrors({})
    try{
      const result=await api.saveDevspace(updates,clearKey)
      setEdits({});setKey('');setCustom({});await load();onSaved?.(result)
      const restart=result.restart_required.length?` Restart the backend to apply ${result.restart_required.join(', ')}.`:''
      setStatus({kind:'ok',text:result.saved.length?`Saved and applied ${result.saved.length} setting${result.saved.length===1?'':'s'}.${restart}`:'Nothing changed.'})
    }catch(e){
      setErrors((e as Error&{errors?:Record<string,string>}).errors||{})
      setStatus({kind:'error',text:(e as Error).message})
    }finally{setSaving(false)}
  }

  async function copy(id:string,text:string){
    try{await navigator.clipboard.writeText(text);setCopied(id);setTimeout(()=>setCopied(current=>current===id?'':current),1500)}
    catch{setStatus({kind:'error',text:'Could not copy. Select the text and copy it manually.'})}
  }

  function input(f:DevspaceField){
    const value=valueOf(f),id=`ds-${f.name}`
    if(f.type==='boolean')return <label className="ds-switch"><input id={id} type="checkbox" checked={Boolean(value)} onChange={e=>change(f,e.target.checked)}/><span>{value?'On':'Off'}</span></label>
    if(f.type==='model'&&!custom[f.name])return <select id={id} value={String(value??'')} onChange={e=>{if(e.target.value==='__custom__')setCustom(c=>({...c,[f.name]:true}));else change(f,e.target.value)}}>
      {(f.options||[]).map(o=><option key={o} value={o}>{o||'Same as chat model'}</option>)}
      <option value="__custom__">Custom…</option>
    </select>
    if(f.type==='choice')return <select id={id} value={String(value??'')} onChange={e=>change(f,e.target.value)}>
      {(f.options||[]).map(o=><option key={o} value={o}>{o||'Default'}</option>)}
    </select>
    if(f.type==='integer'||f.type==='number')return <input id={id} type="number" min={f.min} max={f.max} step={f.type==='integer'?1:'any'} value={value===null?'':String(value)} onChange={e=>change(f,e.target.value===''?null:Number(e.target.value))}/>
    return <input id={id} type="text" value={String(value??'')} placeholder={f.type==='model'?'Model name':''} onChange={e=>change(f,e.target.value)}/>
  }

  if(!data)return <div className="panel-content"><p className="muted">{status?.text||'Loading DevSpace…'}</p></div>
  const pending=Object.keys(edits).length+(key.trim()?1:0)
  return <div className="panel-content devspace">
    <p className="muted">Environment configuration, models & API inspector. Changes are saved to <code>.env</code> and applied right away.</p>
    <div className="ds-tabs" role="tablist">
      <button role="tab" aria-selected={tab==='config'} className={tab==='config'?'active':''} onClick={()=>setTab('config')}>Configuration & Models</button>
      <button role="tab" aria-selected={tab==='prompts'} className={tab==='prompts'?'active':''} onClick={()=>setTab('prompts')}>Prompts & cURL</button>
    </div>

    {tab==='config'?<>
      <section className="ds-card">
        <h3><KeyRound size={15}/> OpenAI API key</h3>
        <span className={`ds-pill ${data.api_key.configured?'on':'off'}`}>{data.api_key.configured?`Key active · ${data.api_key.masked}`:'No key set'}</span>
        <div className="ds-key">
          <input aria-label="OpenAI API key" type={showKey?'text':'password'} value={key} autoComplete="off" spellCheck={false} placeholder={data.api_key.configured?'Paste a new key to replace it':'Paste your OpenAI API key (sk-proj-...)'} onChange={e=>setKey(e.target.value)}/>
          <button type="button" aria-label={showKey?'Hide key':'Show key'} onClick={()=>setShowKey(!showKey)}>{showKey?<EyeOff size={15}/>:<Eye size={15}/>}</button>
        </div>
        {data.api_key.configured&&<button type="button" className="ds-link danger" disabled={saving} onClick={()=>void save(true)}>Remove saved key</button>}
      </section>

      {data.groups.map(group => {
        const GroupIcon = getGroupIcon(group.title)
        return (
          <section className="ds-card" key={group.title}>
            <h3>
              <GroupIcon size={15} aria-hidden="true" style={{ color: 'var(--jade-ink)', flexShrink: 0 }} />
              <span>{group.title}</span>
            </h3>
            <div className="ds-grid">{group.fields.map(f=><div className={`ds-field ${errors[f.name]?'invalid':''}`} key={f.name}>
              <label htmlFor={`ds-${f.name}`}>{f.name}{f.restart_required&&<em>restart needed</em>}{f.name in edits&&<i>edited</i>}</label>
              {input(f)}
              {(f.min!==undefined||f.max!==undefined)&&<small>{f.min??'–'} to {f.max??'–'}</small>}
              {errors[f.name]&&<small className="ds-error">{errors[f.name]}</small>}
            </div>)}</div>
          </section>
        )
      })}

      <footer className="ds-footer">
        {status&&<span role="status" className={status.kind==='error'?'ds-error':'ds-ok'}>{status.text}</span>}
        <button type="button" className="ds-save" disabled={saving||!pending} onClick={()=>void save()}>{saving?'Saving…':pending?`Save & Apply (${pending})`:'Save & Apply'}</button>
      </footer>
    </>:<>
      <h3>System prompts</h3>
      {(Object.keys(PROMPT_LABELS) as (keyof DevspaceData['prompts'])[]).map(id=><details className="ds-block" key={id}>
        <summary>{PROMPT_LABELS[id]}<button type="button" onClick={e=>{e.preventDefault();void copy(id,data.prompts[id])}}>{copied===id?<><Check size={13}/> Copied</>:<><Copy size={13}/> Copy</>}</button></summary>
        <pre>{data.prompts[id]}</pre>
      </details>)}
      <h3>cURL commands</h3>
      {(Object.keys(CURL_LABELS) as (keyof DevspaceData['curl'])[]).map(id=><div className="ds-block open" key={id}>
        <div className="ds-block-head">{CURL_LABELS[id]}<button type="button" onClick={()=>void copy(id,data.curl[id])}>{copied===id?<><Check size={13}/> Copied</>:<><Copy size={13}/> Copy</>}</button></div>
        <pre className="ds-code">{data.curl[id]}</pre>
      </div>)}
      {status&&<p role="status" className={status.kind==='error'?'ds-error':'ds-ok'}>{status.text}</p>}
    </>}
  </div>
}
