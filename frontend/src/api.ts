import type { AgentWorkflow, Conversation, Detail, DevspaceData, DevspaceSaveResult, DevspaceValue, EscalationBundle, KnowledgeBase, Language, PracticeScenario, PracticeSession, PracticeTurn, RoleplayChatResponse, RoleplaySetup, RoleplayStartResponse, StreamEvent, SubmissionAuditStep, UserActionItem } from './types'

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
  bootstrap: () => call<{ai_configured:boolean;devspace_enabled?:boolean;privacy_notice:string;disclaimer:string}>('/api/bootstrap'),
  devspace: () => call<DevspaceData>('/api/system/devspace'),
  // Field errors come back as {detail:{errors:{NAME:message}}}; they ride on the thrown error.
  saveDevspace: async (updates:Record<string,DevspaceValue>, clearApiKey=false):Promise<DevspaceSaveResult> => {
    const response = await fetch('/api/system/devspace',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf())},body:JSON.stringify({updates,clear_api_key:clearApiKey})})
    const payload = await response.json().catch(()=>({}))
    if(!response.ok){const errors=payload.detail?.errors||{};throw Object.assign(new Error(Object.keys(errors).length?'Some settings were not saved.':typeof payload.detail==='string'?payload.detail:'Could not save settings.'),{errors})}
    return payload
  },
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
  setAttachmentConsent:(cid:string,id:string,consented:boolean)=>call<{attachment_id:string;consent_status:'consented'|'withheld'}>(`/api/conversations/${cid}/attachments/${id}/consent`,{method:'POST',body:JSON.stringify({consented})}),
  upload: async (id: string, file: File) => { const body=new FormData(); body.append('file',file); return call<AttachmentUpload>(`/api/conversations/${id}/attachments`,{method:'POST',body}) },
  transcribe: async (file: File) => { const body=new FormData(); body.append('file',file); return call<{transcript:string}>('/api/audio/transcribe',{method:'POST',body}) },
  saveDraft: (cid:string, title:string, content:string) => call(`/api/conversations/${cid}/drafts`,{method:'POST',body:JSON.stringify({title,content})}),
  updateDraft:(cid:string,id:string,title:string,content:string,expected_version:number)=>call<{version:number}>(`/api/conversations/${cid}/drafts/${id}`,{method:'PATCH',body:JSON.stringify({title,content,expected_version})}),
  escalationBundle:(cid:string)=>call<EscalationBundle>(`/api/conversations/${cid}/escalation-bundle`),
  // Fetched in the page and saved from a blob, so it behaves the same in every browser and
  // failures are reported instead of silently opening nothing.
  downloadEscalationBundle: async (cid:string, format:'pdf'|'docx') => {
    const response = await fetch(`/api/conversations/${cid}/escalation-bundle/export/${format}`,{credentials:'include'})
    if(!response.ok)throw new Error(response.status===503?'Busy right now. Please try again shortly.':'The file could not be prepared. Please try again.')
    const filename = /filename="([^"]+)"/.exec(response.headers.get('content-disposition')||'')?.[1] || `nyay-saathi-lawyer-bundle.${format}`
    const url = URL.createObjectURL(await response.blob())
    const link = Object.assign(document.createElement('a'),{href:url,download:filename})
    document.body.appendChild(link);link.click();link.remove()
    setTimeout(()=>URL.revokeObjectURL(url),10_000)
    return filename
  },
  addUserAction:(cid:string,title:string,status:'pending'|'completed'|'skipped'='completed',notes='')=>call<UserActionItem>(`/api/conversations/${cid}/actions`,{method:'POST',body:JSON.stringify({title,status,notes})}),
  updateUserAction:(cid:string,actionId:string,status:'pending'|'completed'|'skipped',notes?:string)=>call<UserActionItem>(`/api/conversations/${cid}/actions/${actionId}`,{method:'PATCH',body:JSON.stringify({status,notes})}),
  recordSubmissionStep:(cid:string,target_channel:string,step:'previewed'|'consented'|'submitted_by_user'|'receipt_captured',draft_id?:string,receipt_reference='',notes='')=>call<SubmissionAuditStep>(`/api/conversations/${cid}/submissions`,{method:'POST',body:JSON.stringify({target_channel,step,draft_id,receipt_reference,notes})}),
  setQualityConsent:(cid:string,opted_in:boolean)=>call<{opted_in:boolean}>(`/api/conversations/${cid}/quality-consent`,{method:'POST',body:JSON.stringify({opted_in})}),
  exportTransfer:(cid:string,passphrase:string)=>call<Record<string,unknown>>(`/api/conversations/${cid}/transfer/export`,{method:'POST',body:JSON.stringify({passphrase})}),
  importTransfer:(bundle:Record<string,unknown>,passphrase:string)=>call<{imported:boolean;conversation:Conversation}>('/api/conversations/transfer/import',{method:'POST',body:JSON.stringify({bundle,passphrase})}),
  rotateCredential:()=>call<{rotated:boolean;csrf_token:string}>('/api/privacy/rotate-credential',{method:'POST',body:'{}'}),
  practiceScenarios:(cid:string)=>call<PracticeScenario[]>(`/api/conversations/${cid}/practice/scenarios`),
  startPracticeSession:(cid:string,payload:{scenario_id:string;custom_scenario?:string;language?:Language})=>call<PracticeSession>(`/api/conversations/${cid}/practice/sessions`,{method:'POST',body:JSON.stringify(payload)}),
  listPracticeSessions:(cid:string)=>call<PracticeSession[]>(`/api/conversations/${cid}/practice/sessions`),
  getPracticeSession:(cid:string,sid:string)=>call<PracticeSession>(`/api/conversations/${cid}/practice/sessions/${sid}`),
  practiceTurn:(cid:string,sid:string,user_argument:string,language:Language)=>call<PracticeTurn>(`/api/conversations/${cid}/practice/sessions/${sid}/turns`,{method:'POST',body:JSON.stringify({user_argument,language})}),
  exportPracticeActions:(cid:string,sid:string,action_titles:string[])=>call<{exported_count:number;status:string}>(`/api/conversations/${cid}/practice/sessions/${sid}/export-actions`,{method:'POST',body:JSON.stringify({action_titles})}),
  roleplaySetup:(cid:string,language:Language='en')=>call<RoleplaySetup>(`/api/conversations/${cid}/roleplay/setup?language=${language}`),
  roleplayStart:(cid:string,stakeholder:string,customStakeholder?:string,language?:Language,setup?:RoleplaySetup|null)=>call<RoleplayStartResponse>(`/api/conversations/${cid}/roleplay/start`,{method:'POST',body:JSON.stringify({stakeholder,custom_stakeholder:customStakeholder,language,case_title:setup?.case_title,case_synopsis:setup?.case_synopsis})}),
  roleplayChat:(cid:string,sessionId:string,message:string,language?:Language)=>call<RoleplayChatResponse>(`/api/conversations/${cid}/roleplay/chat?session_id=${sessionId}`,{method:'POST',body:JSON.stringify({message,language})}),
  // Streams the character's reply: onDelta gets text as it is written, the promise the final result.
  roleplayChatStream: async (cid:string,sessionId:string,message:string,language:Language,onDelta:(text:string)=>void):Promise<RoleplayChatResponse> => {
    const response = await fetch(`/api/conversations/${cid}/roleplay/chat/stream?session_id=${sessionId}`,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf())},body:JSON.stringify({message,language})})
    if(!response.ok || !response.body) throw new Error(response.status===503?'Practice is busy right now. Please try again shortly.':'Could not get a reply. Please retry.')
    const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='',result:RoleplayChatResponse|null=null
    while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value,{stream:!done});let index:number
      while((index=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);const event=frame.split('\n').find(l=>l.startsWith('event: '))?.slice(7);const data=frame.split('\n').filter(l=>l.startsWith('data: ')).map(l=>l.slice(6)).join('\n');if(!data)continue;const payload=JSON.parse(data);if(event==='delta'&&typeof payload.text==='string')onDelta(payload.text);if(event==='result')result=payload;if(event==='error')throw new Error('This practice session has ended. Start a new one.')}
      if(done)break
    }
    if(!result)throw new Error('Connection interrupted. Please retry.')
    return result
  },
}

interface AttachmentUpload { id:string; filename:string; extraction_status:string }
