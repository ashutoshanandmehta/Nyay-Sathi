import type { AgentWorkflow, Conversation, Detail, KnowledgeBase, Language, StreamEvent } from './types'

const csrf = () => document.cookie.split('; ').find(x => x.startsWith('nyay_csrf='))?.split('=').slice(1).join('=') ?? ''

async function call<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (init.method && init.method !== 'GET') headers.set('X-CSRF-Token', decodeURIComponent(csrf()))
  const response = await fetch(url, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({detail: response.statusText}))
    throw new Error(typeof payload.detail === 'string' ? payload.detail : payload.detail?.code ?? 'Request failed')
  }
  return response.json() as Promise<T>
}

export const api = {
  bootstrap: () => call<{ai_configured:boolean;privacy_notice:string;disclaimer:string}>('/api/bootstrap'),
  knowledgeBase: () => call<KnowledgeBase>('/api/system/knowledge-base'),
  agentWorkflow: () => call<AgentWorkflow>('/api/system/agent-workflow'),
  list: () => call<Conversation[]>('/api/conversations'),
  create: (language: Language) => call<Conversation>('/api/conversations', {method:'POST', body:JSON.stringify({language})}),
  detail: (id: string) => call<Detail>(`/api/conversations/${id}`),
  rename: (id: string, title: string) => call(`/api/conversations/${id}`, {method:'PATCH', body:JSON.stringify({title})}),
  remove: (id: string) => call(`/api/conversations/${id}`, {method:'DELETE'}),
  turn: (id: string, content: string, language: Language, requestId: string, attachmentIds: string[]) =>
    call<{assistant_message: Detail['messages'][number]}>(`/api/conversations/${id}/turns`, {method:'POST', body:JSON.stringify({content,language,request_id:requestId,attachment_ids:attachmentIds})}),
  streamTurn: async (id:string, content:string, language:Language, requestId:string, attachmentIds:string[], progress:(event:StreamEvent)=>void) => {
    const response = await fetch(`/api/conversations/${id}/turns/stream`, {method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf())},body:JSON.stringify({content,language,request_id:requestId,attachment_ids:attachmentIds})})
    if(!response.ok || !response.body) throw new Error('Could not start this turn. Please retry.')
    const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='',completed=false
    while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value,{stream:!done});let index:number
      while((index=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);const event=frame.split('\n').find(l=>l.startsWith('event: '))?.slice(7);const data=frame.split('\n').filter(l=>l.startsWith('data: ')).map(l=>l.slice(6)).join('\n');if(!data)continue;const payload=JSON.parse(data);if(event==='progress')progress(payload);if(event==='safety'&&payload.type==='safety'&&typeof payload.content_id==='string'&&typeof payload.text==='string'&&payload.text.length<=5000)progress({...payload,stage:'safety',request_id:requestId});if(event==='result')completed=true;if(event==='error')throw new Error(typeof payload.detail==='string'?payload.detail:payload.detail?.code||'Turn failed; your message is saved.')}
      if(done)break
    }
    if(!completed)throw new Error('Connection interrupted. Your message may still be processing; retry safely.')
  },
  correctAttachment:(cid:string,id:string,extracted_text:string)=>call(`/api/conversations/${cid}/attachments/${id}`,{method:'PATCH',body:JSON.stringify({extracted_text})}),
  upload: async (id: string, file: File) => { const body=new FormData(); body.append('file',file); return call<Attachment>(`/api/conversations/${id}/attachments`,{method:'POST',body}) },
  transcribe: async (file: File) => { const body=new FormData(); body.append('file',file); return call<{transcript:string}>('/api/audio/transcribe',{method:'POST',body}) },
  saveDraft: (cid:string, title:string, content:string) => call(`/api/conversations/${cid}/drafts`,{method:'POST',body:JSON.stringify({title,content})}),
  updateDraft:(cid:string,id:string,title:string,content:string,expected_version:number)=>call<{version:number}>(`/api/conversations/${cid}/drafts/${id}`,{method:'PATCH',body:JSON.stringify({title,content,expected_version})}),
}

interface Attachment { id:string; filename:string; extraction_status:string }
