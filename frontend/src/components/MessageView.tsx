import { Check, Copy, RotateCcw, Volume2 } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, Source } from '../types'

export default function MessageView({message,onSources,onRetry,onSpeech}:{message:Message;onSources:(s:Source[])=>void;onRetry?:()=>void;onSpeech?:()=>void}) {
  const [copied,setCopied]=useState(false)
  async function copy(){await navigator.clipboard.writeText(message.content);setCopied(true);setTimeout(()=>setCopied(false),1200)}
  const needsConfirmation=message.metadata?.events?.some(event=>event.status==='confirmation_required')
  return <article className={`message ${message.role}`}>
    <div className="avatar" aria-hidden>{message.role==='assistant'?'न्या':'You'}</div>
    <div className="message-body"><div className="message-role">{message.role==='assistant'?'Nyay Saathi':'You'}</div>
      {message.role==='assistant'?<ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{message.content}</ReactMarkdown>:<p>{message.content}</p>}
      {message.metadata?.publication_status==='partial'&&<small className="muted" role="note">Some help is ready. Unverified parts have been left out.</small>}
      {!!message.metadata?.attachment_ids?.length&&<small className="muted">{message.metadata.attachment_ids.length} attached document(s) · view in Your case</small>}
      {needsConfirmation&&<div className="confirmation-card" role="note"><b>One detail needs review</b><span>Reply naturally with the correct detail. You do not need to use a special confirmation phrase.</span></div>}
      <div className="message-actions">
        <button onClick={copy}>{copied?<Check size={15}/>:<Copy size={15}/>} {copied?'Copied':'Copy'}</button>
        {message.metadata?.sources?.length?<button onClick={()=>onSources(message.metadata.sources!)}>Sources · {message.metadata.sources.length}</button>:null}
        {onSpeech&&(message.metadata?.verification?.passed||message.metadata?.verification?.publication_safe)&&<button onClick={onSpeech}><Volume2 size={15}/> Listen</button>}
        {message.status==='failed'&&onRetry&&<button onClick={onRetry}><RotateCcw size={15}/> Retry</button>}
      </div>
    </div>
  </article>
}
