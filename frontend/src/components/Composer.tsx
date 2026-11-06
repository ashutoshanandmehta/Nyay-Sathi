import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Mic, Paperclip, Square, X } from 'lucide-react'
import { api } from '../api'

export default function Composer({disabled, initial='', onSend, onUpload, onRemove}:{disabled:boolean;initial?:string;onSend:(text:string)=>Promise<boolean>;onUpload:(id:string,name:string)=>void;onRemove?:(id:string)=>void}) {
  const [text,setText]=useState(initial), [recording,setRecording]=useState(false), [uploading,setUploading]=useState(false)
  const [attachments,setAttachments]=useState<{id:string;name:string;status:string}[]>([]), [error,setError]=useState('')
  const input=useRef<HTMLTextAreaElement>(null), media=useRef<MediaRecorder|null>(null), chunks=useRef<Blob[]>([])
  useEffect(()=>{ if(input.current){ input.current.style.height='auto'; input.current.style.height=Math.min(input.current.scrollHeight,180)+'px' } },[text])
  async function submit(){ if(!text.trim()||disabled||uploading)return; const snapshot=text.trim(), files=attachments;setError('');setText('');setAttachments([]);try{const ok=await onSend(snapshot);if(!ok){setText(current=>current||snapshot);setAttachments(files)}}catch{setText(current=>current||snapshot);setAttachments(files);setError('Could not send. Your draft is preserved.')} }
  async function upload(file?:File){ if(!file||disabled)return; setUploading(true);setError(''); try{ const item=await api.upload(location.pathname.split('/').pop()||'',file); setAttachments(a=>[...a,{id:item.id,name:item.filename,status:item.extraction_status}]);onUpload(item.id,item.filename) }catch(e){setError((e as Error).message)}finally{setUploading(false)} }
  async function toggleRecording(){
    if(recording){media.current?.stop();setRecording(false);return}
    try{ const stream=await navigator.mediaDevices.getUserMedia({audio:true}); const recorder=new MediaRecorder(stream);chunks.current=[];recorder.ondataavailable=e=>chunks.current.push(e.data); recorder.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());try{const blob=new Blob(chunks.current,{type:recorder.mimeType});const result=await api.transcribe(new File([blob],'recording.webm',{type:blob.type}));setText(t=>t?`${t}\n${result.transcript}`:result.transcript)}catch(e){setError((e as Error).message)}};recorder.start();media.current=recorder;setRecording(true)
    }catch{setError('Microphone permission was not available.')}
  }
  return <div className="composer-wrap">
    {attachments.length>0&&<div className="attachment-row">{attachments.map(a=><span className="chip" key={a.id}>{a.name} · {a.status==='complete'?'Ready':a.status.replaceAll('_',' ')}<button aria-label={`Remove ${a.name}`} onClick={()=>{setAttachments(x=>x.filter(v=>v.id!==a.id));onRemove?.(a.id)}}><X size={13}/></button></span>)}</div>}
    <div className={`composer ${recording?'recording':''}`}>
      <label className="icon-button" aria-label="Attach PDF, image, or text"><Paperclip size={20}/><input type="file" disabled={disabled||uploading} accept=".pdf,.png,.jpg,.jpeg,.txt" hidden onChange={e=>{void upload(e.target.files?.[0]);e.target.value=''}}/></label>
      <textarea ref={input} value={text} disabled={disabled} placeholder="Describe what happened…" aria-label="Message" rows={1}
        onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();submit()}}}/>
      <button className="icon-button" aria-label={recording?'Stop recording':'Record voice'} onClick={toggleRecording}>{recording?<Square size={18}/>:<Mic size={20}/>}</button>
      <button className="send" disabled={disabled||uploading||!text.trim()} aria-label="Send message" onClick={submit}><ArrowUp size={19}/></button>
    </div>
    {(uploading||recording||error)&&<div className={`composer-status ${error?'error':''}`} role="status">{uploading?'Uploading and extracting…':recording?'Recording — tap stop when finished':error}</div>}
    <div className="fine-print">Nyay Saathi provides legal information and preparation help, not legal representation.</div>
  </div>
}
