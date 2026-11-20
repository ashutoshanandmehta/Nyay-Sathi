import type { AgentWorkflow, CaseRecord, Conversation, Detail, DevspaceData, DevspaceSaveResult, DevspaceValue, DriveFolderInfo, DriveManifestRecord, EscalationBundle, GmailApproval, GmailDispatch, GmailEvidenceMessage, GoogleProviderConnection, KnowledgeBase, Language, PracticeScenario, PracticeSession, PracticeTurn, RoleplayChatResponse, RoleplaySetup, RoleplayStartResponse, StreamEvent, SubmissionAuditStep, UserActionItem, VerifiedContact } from './types'
import { apiFetch } from './byok'
import { backendConfig } from './backend'

export interface UserKeyStatus { stored: boolean; unlocked: boolean; hint: string | null; server_key: boolean }

export interface NativeFilesBridge {
  saveAndShareBase64File(filename: string, mimeType: string, base64Data: string): boolean | Promise<boolean>
}

declare global {
  interface Window {
    NyayNativeFiles?: NativeFilesBridge
    __nyayHandleBackPress?: () => boolean
    __nyayPendingOAuthCallback?: {
      url?: string
      provider?: string
      code?: string
      state?: string
      error?: string
    }
  }
}

async function blobToBase64(blob: Blob): Promise<string> {
  if (typeof blob.arrayBuffer === 'function') {
    const buf = await blob.arrayBuffer()
    const bytes = new Uint8Array(buf)
    let binary = ''
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i])
    }
    return btoa(binary)
  }
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const res = typeof reader.result === 'string' ? reader.result : ''
      const comma = res.indexOf(',')
      resolve(comma >= 0 ? res.slice(comma + 1) : res)
    }
    reader.onerror = () => reject(reader.error || new Error('Could not read file blob'))
    reader.readAsDataURL(blob)
  })
}

async function saveOrDownloadBlob(blob: Blob, filename: string, mimeType: string): Promise<string> {
  if (typeof window !== 'undefined' && window.NyayNativeFiles?.saveAndShareBase64File) {
    const b64 = await blobToBase64(blob)
    const handled = await window.NyayNativeFiles.saveAndShareBase64File(filename, mimeType, b64)
    if (handled) return filename
  }
  if (
    typeof navigator !== 'undefined' &&
    typeof navigator.share === 'function' &&
    typeof navigator.canShare === 'function' &&
    typeof File === 'function'
  ) {
    try {
      const file = new File([blob], filename, { type: mimeType })
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: filename })
        return filename
      }
    } catch {
      // Fall through to browser download link if user cancels or Web Share fails
    }
  }
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
  return filename
}

const csrf = () => document.cookie.split('; ').find(x => x.startsWith('nyay_csrf='))?.split('=').slice(1).join('=') ?? ''

async function call<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (init.method && init.method !== 'GET') headers.set('X-CSRF-Token', decodeURIComponent(csrf()))
  const response = await apiFetch(url, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({detail: response.statusText}))
    throw new Error(typeof payload.detail === 'string' ? payload.detail : payload.detail?.code ?? 'Request failed')
  }
  return response.json() as Promise<T>
}

type ResumableStatus = {request_id:string; execution_id:string; status:string; error_detail?:{detail?:string}}
type ReplayEvent = {seq:number; kind:string; request_id:string; execution_id:string; payload:Partial<StreamEvent>}
const turnPath = (chat:string, request:string) => `/api/conversations/${chat}/turns/${encodeURIComponent(request)}`

async function followTurn(chat:string, request:string, progress:(event:StreamEvent)=>void, cursor=0) {
  let failures=0
  for (;;) {
    let page:{turn:ResumableStatus;events:ReplayEvent[]}
    try {
      page=await call(`${turnPath(chat,request)}/events?after_seq=${cursor}`,{signal:AbortSignal.timeout(10_000)})
      failures=0
    } catch (error) {
      if(++failures>=5) throw error
      await new Promise(resolve=>setTimeout(resolve,1000*failures))
      continue
    }
    for(const event of page.events) {
      if(event.seq<=cursor) continue
      cursor=event.seq
      if(event.kind==='safety' || event.kind==='answer_block' || event.kind==='progress') {
        progress({stage:event.kind,...event.payload,
          ...(event.kind==='progress' ? {} : {type:event.kind}),
          request_id:event.request_id,execution_id:event.execution_id,seq:event.seq})
      }
    }
    if(page.events.length===100) continue
    if(page.turn.status==='completed') return
    if(['interrupted','failed'].includes(page.turn.status)) {
      throw new Error(page.turn.error_detail?.detail || 'Turn ended before an answer was published.')
    }
    await new Promise(resolve=>setTimeout(resolve,1500))
  }
}

export const api = {
  bootstrap: () => call<{ai_configured:boolean;devspace_enabled?:boolean;privacy_notice:string;disclaimer:string}>('/api/bootstrap'),
  devspace: () => call<DevspaceData>('/api/system/devspace'),
  userKey: () => call<UserKeyStatus>('/api/me/openai-key'),
  saveUserKey: (apiKey: string) => call<UserKeyStatus>('/api/me/openai-key', {method:'PUT', body:JSON.stringify({api_key:apiKey})}),
  removeUserKey: () => call<UserKeyStatus>('/api/me/openai-key', {method:'DELETE'}),
  // Field errors come back as {detail:{errors:{NAME:message}}}; they ride on the thrown error.
  saveDevspace: async (updates:Record<string,DevspaceValue>, clearApiKey=false):Promise<DevspaceSaveResult> => {
    const response = await apiFetch('/api/system/devspace',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf())},body:JSON.stringify({updates,clear_api_key:clearApiKey})})
    const payload = await response.json().catch(()=>({}))
    if(!response.ok){const errors=payload.detail?.errors||{};throw Object.assign(new Error(Object.keys(errors).length?'Some settings were not saved.':typeof payload.detail==='string'?payload.detail:'Could not save settings.'),{errors})}
    return payload
  },
  knowledgeBase: () => call<KnowledgeBase>('/api/system/knowledge-base'),
  agentWorkflow: () => call<AgentWorkflow>('/api/system/agent-workflow'),
  list: () => call<Conversation[]>('/api/conversations'),
  create: (language: Language, caseId?: string) => call<Conversation>('/api/conversations', {method:'POST', body:JSON.stringify(caseId ? {language, case_id: caseId} : {language})}),
  detail: (id: string) => call<Detail>(`/api/conversations/${id}`),
  rename: (id: string, title: string) => call(`/api/conversations/${id}`, {method:'PATCH', body:JSON.stringify({title})}),
  remove: (id: string) => call(`/api/conversations/${id}`, {method:'DELETE'}),
  turn: async (id: string, content: string, language: Language, requestId: string, attachmentIds: string[]) => {
    if (backendConfig().mode==='supabase') {
      await api.streamTurn(id,content,language,requestId,attachmentIds,()=>undefined)
      const {turn}=await call<{turn:ResumableStatus & {result:{assistant_message:Detail['messages'][number]}}}>(turnPath(id,requestId))
      return turn.result
    }
    return call<{assistant_message: Detail['messages'][number]}>(`/api/conversations/${id}/turns`, {method:'POST', body:JSON.stringify({content,language,request_id:requestId,attachment_ids:attachmentIds})})
  },
  activeTurn: async (id:string) => backendConfig().mode==='supabase'
    ? (await call<{turn:ResumableStatus|null}>(turnPath(id,'active'))).turn : null,
  resumeTurn: followTurn,
  cancelTurn: (id:string,request:string) => call(`${turnPath(id,request)}/cancel`,{method:'POST'}),
  streamTurn: async (id:string, content:string, language:Language, requestId:string, attachmentIds:string[], progress:(event:StreamEvent)=>void, afterSeq=0) => {
    if (backendConfig().mode === 'supabase') {
      await call(`/api/conversations/${id}/turns`,{
        method:'POST',body:JSON.stringify({content,language,request_id:requestId,attachment_ids:attachmentIds}),
      })
      return followTurn(id, requestId, progress, afterSeq)
    }
    const query = afterSeq > 0 ? `?after_seq=${afterSeq}` : ''
    const response = await apiFetch(`/api/conversations/${id}/turns/stream${query}`, {method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf()),...(afterSeq > 0 ? {'Last-Event-ID': String(afterSeq)} : {})},body:JSON.stringify({content,language,request_id:requestId,attachment_ids:attachmentIds})})
    if(!response.ok || !response.body) throw new Error('Could not start this turn. Please retry.')
    const reader=response.body.getReader(), decoder=new TextDecoder();let buffer='',completed=false,lastSeq=afterSeq,activeExecId:string|null=null;const seenRevisions=new Set<string>()
    while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value,{stream:!done});let index:number
      while((index=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);const event=frame.split('\n').find(l=>l.startsWith('event: '))?.slice(7);const idLine=frame.split('\n').find(l=>l.startsWith('id: '))?.slice(4);const data=frame.split('\n').filter(l=>l.startsWith('data: ')).map(l=>l.slice(6)).join('\n');if(!data)continue;const payload=JSON.parse(data);if(payload.publication_status==='superseded'||payload.publication_status==='withheld')continue;if(typeof payload.execution_id==='string'&&payload.execution_id){if(activeExecId&&activeExecId!==payload.execution_id){seenRevisions.clear()}activeExecId=payload.execution_id}const seq=typeof payload.seq==='number'?payload.seq:(idLine?Number(idLine):undefined);if(typeof seq==='number'&&!Number.isNaN(seq)){if(seq<=lastSeq)continue;lastSeq=seq}if(event==='progress')progress(payload);if(event==='safety'&&payload.type==='safety'&&typeof payload.content_id==='string'&&typeof payload.text==='string'&&payload.text.length<=5000)progress({...payload,stage:'safety',request_id:requestId});if(event==='answer_block'&&payload.block&&typeof payload.block.block_id==='string'&&typeof payload.block.content==='string'){const revKey=`${payload.execution_id||requestId}:${payload.block.block_id}:${payload.block_revision||1}`;if(!seenRevisions.has(revKey)){seenRevisions.add(revKey);progress({...payload,type:'answer_block',stage:'answer_block',request_id:requestId})}}if(event==='result')completed=true;if(event==='error')throw new Error(typeof payload.detail==='string'?payload.detail:payload.detail?.code||'Turn failed; your message is saved.')}
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
    const response = await apiFetch(`/api/conversations/${cid}/escalation-bundle/export/${format}`,{credentials:'include'})
    if(!response.ok)throw new Error(response.status===503?'Busy right now. Please try again shortly.':'The file could not be prepared. Please try again.')
    const filename = /filename="([^"]+)"/.exec(response.headers.get('content-disposition')||'')?.[1] || `nyay-saathi-lawyer-bundle.${format}`
    const mimeType = format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return saveOrDownloadBlob(await response.blob(), filename, mimeType)
  },
  downloadCaseExport: async (cid:string, format:'json'|'docx'|'pdf') => {
    const response = await apiFetch(`/api/conversations/${cid}/export/${format}`,{credentials:'include'})
    if(!response.ok)throw new Error(response.status===503?'Busy right now. Please try again shortly.':'The export could not be prepared. Please try again.')
    const filename = /filename="([^"]+)"/.exec(response.headers.get('content-disposition')||'')?.[1] || `nyay-saathi-case-pack.${format}`
    const mimeType = format === 'json' ? 'application/json' : format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return saveOrDownloadBlob(await response.blob(), filename, mimeType)
  },
  downloadDraftExport: async (cid:string, draftId:string, format:'pdf'|'docx') => {
    const response = await apiFetch(`/api/conversations/${cid}/drafts/${draftId}/export/${format}`,{credentials:'include'})
    if(!response.ok)throw new Error(response.status===503?'Busy right now. Please try again shortly.':'The draft could not be prepared. Please try again.')
    const filename = /filename="([^"]+)"/.exec(response.headers.get('content-disposition')||'')?.[1] || `prepared-correspondence.${format}`
    const mimeType = format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return saveOrDownloadBlob(await response.blob(), filename, mimeType)
  },
  addUserAction:(cid:string,title:string,status:'pending'|'completed'|'skipped'='completed',notes='')=>call<UserActionItem>(`/api/conversations/${cid}/actions`,{method:'POST',body:JSON.stringify({title,status,notes})}),
  updateUserAction:(cid:string,actionId:string,status:'pending'|'completed'|'skipped',notes?:string)=>call<UserActionItem>(`/api/conversations/${cid}/actions/${actionId}`,{method:'PATCH',body:JSON.stringify({status,notes})}),
  recordSubmissionStep:(cid:string,target_channel:string,step:'previewed'|'consented'|'submitted_by_user'|'receipt_captured',draft_id?:string,receipt_reference='',notes='')=>call<SubmissionAuditStep>(`/api/conversations/${cid}/submissions`,{method:'POST',body:JSON.stringify({target_channel,step,draft_id,receipt_reference,notes})}),
  setQualityConsent:(cid:string,opted_in:boolean)=>call<{opted_in:boolean}>(`/api/conversations/${cid}/quality-consent`,{method:'POST',body:JSON.stringify({opted_in})}),
  exportTransfer:(cid:string,passphrase:string)=>call<Record<string,unknown>>(`/api/conversations/${cid}/transfer/export`,{method:'POST',body:JSON.stringify({passphrase})}),
  importTransfer:(bundle:Record<string,unknown>,passphrase:string)=>call<{imported:boolean;conversation:Conversation}>('/api/conversations/transfer/import',{method:'POST',body:JSON.stringify({bundle,passphrase})}),
  rotateCredential:()=>call<{rotated:boolean;csrf_token:string}>('/api/privacy/rotate-credential',{method:'POST',body:'{}'}),
  // Package 4: Independent Cases, Lifecycle State & Verified Contact Registry
  listCases:()=>call<CaseRecord[]>('/api/cases'),
  getCase:(caseId:string)=>call<{case:CaseRecord;conversations:Conversation[]}>(`/api/cases/${caseId}`),
  updateLifecycle:(cid:string,payload:{event_kind:'submission'|'promise'|'processed_refund'|'remedy_receipt'|'closure';entry?:Record<string,unknown>;closure_status?:string;domain?:string})=>call<Record<string,unknown>>(`/api/conversations/${cid}/lifecycle`,{method:'POST',body:JSON.stringify(payload)}),
  verifiedContacts:()=>call<{as_of:string;contacts:VerifiedContact[];suppressed_expired_count:number}>('/api/contacts/verified'),
  // Packages 5 & 6: Google Drive & Gmail Integrations
  googleStatus:()=>call<{owner_id:string;google_drive:GoogleProviderConnection|null;google_gmail:GoogleProviderConnection|null;storage_policy:string}>('/api/integrations/google/status'),
  connectGoogle:(payload:{provider:'google_drive'|'google_gmail';provider_account_email:string;granted_scopes:string[];access_token:string;refresh_token?:string;reply_monitoring_opted_in?:boolean})=>call<{connected:boolean;connection:GoogleProviderConnection;oauth_secrets_isolated:boolean}>('/api/integrations/google/connect',{method:'POST',body:JSON.stringify(payload)}),
  disconnectGoogle:(provider:'google_drive'|'google_gmail')=>call<{revoked:boolean;provider:string;secrets_purged:boolean}>('/api/integrations/google/disconnect',{method:'POST',body:JSON.stringify({provider})}),
  setGmailReplyMonitoring:(opted_in:boolean)=>call<{reply_monitoring_opted_in:boolean;auto_send_enabled:boolean;auto_escalation_enabled:boolean;note:string}>('/api/integrations/google/gmail-monitoring',{method:'PATCH',body:JSON.stringify({opted_in})}),
  driveManifest:(cid:string)=>call<{case_id:string;connection:GoogleProviderConnection|null;folder:DriveFolderInfo|null;items:DriveManifestRecord[];local_v2_migration_policy:string}>(`/api/conversations/${cid}/drive/manifest`),
  createDriveFolder:(cid:string)=>call<DriveFolderInfo>(`/api/conversations/${cid}/drive/folder`,{method:'POST',body:'{}'}),
  uploadToDrive:(cid:string,payload:{filename:string;mime_type?:string;text?:string;content_base64?:string;evidence_type?:string;provenance?:'user_uploaded_original'|'user_selected_drive_file'|'local_v2_disclosed_explicit'})=>call<{item:DriveManifestRecord;duplicate_reused:boolean}>(`/api/conversations/${cid}/drive/upload`,{method:'POST',body:JSON.stringify(payload)}),
  reconcileDrive:(cid:string,provider_file_states:Record<string,'present'|'moved'|'trashed'|'missing'>={})=>call<{case_id:string;connection_status:string;summary:Record<string,number>;items:DriveManifestRecord[]}>(`/api/conversations/${cid}/drive/reconcile`,{method:'POST',body:JSON.stringify({provider_file_states})}),
  cleanupTemporaryDriveData:(cid:string)=>call<{case_id:string;temporary_artifacts_cleaned:number;status:string}>(`/api/conversations/${cid}/drive/cleanup-temporary`,{method:'POST',body:'{}'}),
  gmailState:(cid:string)=>call<{case_id:string;connection:GoogleProviderConnection|null;evidence_messages:GmailEvidenceMessage[];approvals:GmailApproval[];dispatches:GmailDispatch[]}>(`/api/conversations/${cid}/gmail/state`),
  importGmailEvidence:(cid:string,payload:{gmail_message_id:string;gmail_thread_id?:string;sender:string;recipient?:string;subject:string;snippet?:string;body_text?:string})=>call<{imported:GmailEvidenceMessage;untrusted_data_isolation:{passive_evidence_only:boolean;can_modify_recipients_or_tools:boolean;flags_detected:string[]}}>(`/api/conversations/${cid}/gmail/import`,{method:'POST',body:JSON.stringify(payload)}),
  createGmailApproval:(cid:string,payload:{to_recipients:string[];cc_recipients?:string[];bcc_recipients?:string[];subject:string;body:string;selected_attachment_ids:string[];reply_thread_id?:string|null})=>call<GmailApproval>(`/api/conversations/${cid}/gmail/approvals`,{method:'POST',body:JSON.stringify(payload)}),
  sendApprovedGmail:(cid:string,payload:{approval_id:string;to_recipients:string[];cc_recipients?:string[];bcc_recipients?:string[];subject:string;body:string;selected_attachment_ids:string[];reply_thread_id?:string|null;simulate_ambiguous_timeout?:boolean})=>call<{sent:boolean;dispatch:GmailDispatch;event_classification:string;notice:string}>(`/api/conversations/${cid}/gmail/send`,{method:'POST',body:JSON.stringify(payload)}),
  reconcileGmailSend:(cid:string,payload:{approval_id:string;provider_sent_found:boolean;gmail_message_id?:string})=>call<{reconciled:boolean;outcome:string;dispatch:GmailDispatch}>(`/api/conversations/${cid}/gmail/reconcile`,{method:'POST',body:JSON.stringify(payload)}),
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
    const response = await apiFetch(`/api/conversations/${cid}/roleplay/chat/stream?session_id=${sessionId}`,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf())},body:JSON.stringify({message,language})})
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
