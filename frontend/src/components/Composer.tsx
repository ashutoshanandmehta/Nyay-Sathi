import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Mic, Paperclip, X } from 'lucide-react'
import { api } from '../api'
import { prewarm, startLiveTranscription, type LiveRecording, type VoiceState } from '../voice'
import './voice.css'

// A hold shorter than this is treated as an accidental tap: nothing starts, nothing is spent.
export const HOLD_MS = 250
// Space talks only from the mic button or when nothing is focused, so typing a space and
// pressing Space on other buttons keep working as usual.
const spaceTalks = (el: Element | null) => !el || el === document.body || el.classList.contains('mic-button')

export default function Composer({disabled, initial='', onSend, onUpload, onRemove}:{disabled:boolean;initial?:string;onSend:(text:string)=>Promise<boolean>;onUpload:(id:string,name:string)=>void;onRemove?:(id:string)=>void}) {
  const [text,setText]=useState(initial), [uploading,setUploading]=useState(false)
  const [attachments,setAttachments]=useState<{id:string;name:string;status:string}[]>([]), [error,setError]=useState('')
  const [voice,setVoice]=useState<VoiceState|'idle'>('idle'), [live,setLive]=useState({final:'',partial:''})
  const [level,setLevel]=useState(0), [seconds,setSeconds]=useState(0), [hint,setHint]=useState('')
  const input=useRef<HTMLTextAreaElement>(null)
  // 'pending' = pressed but under HOLD_MS; 'active' = recording started (or starting).
  const phase=useRef<'idle'|'pending'|'active'>('idle'), holdTimer=useRef(0), held=useRef(false)
  const recording=useRef<Promise<LiveRecording|null>|null>(null)
  useEffect(()=>{ if(input.current){ input.current.style.height='auto'; input.current.style.height=Math.min(input.current.scrollHeight,180)+'px' } },[text])
  useEffect(()=>{ if(voice!=='listening')return; setSeconds(0); const t=setInterval(()=>setSeconds(s=>s+1),1000); return ()=>clearInterval(t) },[voice])
  async function submit(){ if(!text.trim()||disabled||uploading||voice!=='idle')return; const snapshot=text.trim(), files=attachments;setError('');setText('');setAttachments([]);try{const ok=await onSend(snapshot);if(!ok){setText(current=>current||snapshot);setAttachments(files)}}catch{setText(current=>current||snapshot);setAttachments(files);setError('Could not send. Your draft is preserved.')} }
  async function upload(file?:File){ if(!file||disabled)return; setUploading(true);setError(''); try{ const item=await api.upload(location.pathname.split('/').pop()||'',file); setAttachments(a=>[...a,{id:item.id,name:item.filename,status:item.extraction_status}]);onUpload(item.id,item.filename) }catch(e){setError((e as Error).message)}finally{setUploading(false)} }

  function reset(){ phase.current='idle'; recording.current=null; setVoice('idle'); setLive({final:'',partial:''}); setLevel(0) }
  function press(){
    if(disabled||phase.current!=='idle')return
    held.current=true; phase.current='pending'; setHint(''); setError('')
    holdTimer.current=window.setTimeout(()=>{ if(held.current)begin() },HOLD_MS)
  }
  function begin(){
    phase.current='active'
    recording.current=startLiveTranscription({
      onText:(final,partial)=>setLive({final,partial}),
      onState:setVoice,
      onLevel:setLevel,
      onLimit:release,
    }).catch(()=>{ setError('Microphone permission was not available.'); reset(); return null })
  }
  function release(){
    if(!held.current)return
    held.current=false
    if(phase.current==='pending'){ clearTimeout(holdTimer.current); phase.current='idle'; setHint('Hold to talk, or hold Space'); return }
    if(phase.current==='active')void finish()
  }
  async function finish(){
    const recorder=await recording.current
    if(!recorder)return
    try{
      const transcript=await recorder.stop()
      if(transcript){
        setText(current=>current?`${current}\n${transcript}`:transcript)
        requestAnimationFrame(()=>{ const box=input.current; if(box){ box.focus(); box.setSelectionRange(box.value.length,box.value.length) } })
      }else setError('No speech was picked up. Hold the mic and speak, then release.')
    }catch(e){ setError((e as Error).message||'Transcription failed. Please try again or type your message.') }
    finally{ reset() }
  }
  async function cancel(){
    held.current=false; clearTimeout(holdTimer.current)
    const recorder=await recording.current
    recorder?.cancel(); reset()
  }

  // Space to talk; Esc cancels; leaving the window finishes and keeps what was said.
  const handlers=useRef({press,release,cancel}); handlers.current={press,release,cancel}
  useEffect(()=>{
    const down=(e:KeyboardEvent)=>{
      if(e.key==='Escape'&&phase.current!=='idle'){ e.preventDefault(); void handlers.current.cancel(); return }
      if(e.code!=='Space'||!spaceTalks(document.activeElement))return
      e.preventDefault()
      if(!e.repeat)handlers.current.press()
    }
    const up=(e:KeyboardEvent)=>{ if(e.code==='Space'&&held.current){ e.preventDefault(); handlers.current.release() } }
    const leave=()=>{ if(held.current)handlers.current.release() }
    const hidden=()=>{ if(document.visibilityState==='hidden')leave() }
    window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',leave);document.addEventListener('visibilitychange',hidden)
    return ()=>{window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',leave);document.removeEventListener('visibilitychange',hidden)}
  },[])

  const busy=voice!=='idle'
  const status=uploading?'Uploading and extracting…':voice==='connecting'?'Connecting…':voice==='listening'?`Listening ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} · release to finish, Esc to cancel`:voice==='finishing'?'Finishing transcript…':error||hint
  return <div className="composer-wrap">
    {attachments.length>0&&<div className="attachment-row">{attachments.map(a=><span className="chip" key={a.id}>{a.name} · {a.status==='complete'?'Ready':a.status.replaceAll('_',' ')}<button aria-label={`Remove ${a.name}`} onClick={()=>{setAttachments(x=>x.filter(v=>v.id!==a.id));onRemove?.(a.id)}}><X size={13}/></button></span>)}</div>}
    {busy&&<div className="voice-live" aria-live="polite">{live.final}{live.partial&&<em> {live.partial}</em>}{!live.final&&!live.partial&&<span className="voice-placeholder">{voice==='finishing'?'Finishing…':'Speak now…'}</span>}</div>}
    <div className={`composer ${busy?'recording':''}`}>
      <label className="icon-button" aria-label="Attach PDF, image, or text"><Paperclip size={20}/><input type="file" disabled={disabled||uploading} accept=".pdf,.png,.jpg,.jpeg,.txt" hidden onChange={e=>{void upload(e.target.files?.[0]);e.target.value=''}}/></label>
      <textarea ref={input} value={text} disabled={disabled} placeholder="Describe what happened…" aria-label="Message" rows={1}
        onFocus={()=>{void prewarm()}}
        onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();submit()}}}/>
      <button type="button" className={`icon-button mic-button ${voice}`} disabled={disabled||voice==='finishing'}
        aria-label="Hold to talk, or hold Space" title="Hold to talk · or hold Space"
        style={{['--level' as string]:level}}
        onPointerEnter={()=>{void prewarm()}}
        onPointerDown={e=>{e.preventDefault();e.currentTarget.setPointerCapture?.(e.pointerId);press()}}
        onPointerUp={release} onPointerCancel={release}
        onContextMenu={e=>e.preventDefault()}><Mic size={20}/></button>
      <button className="send" disabled={disabled||uploading||busy||!text.trim()} aria-label="Send message" onClick={submit}><ArrowUp size={19}/></button>
    </div>
    {status&&<div className={`composer-status ${error&&!busy&&!uploading?'error':''}`} role="status">{status}</div>}
    <div className="fine-print">Nyay Saathi provides legal information and preparation help, not legal representation.</div>
  </div>
}
