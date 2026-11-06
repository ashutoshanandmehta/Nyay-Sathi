import { useState } from 'react'
import { api } from '../api'
import type { Draft } from '../types'

export default function DraftEditor({draft,caseId}:{draft:Draft;caseId:string}){
  const [content,setContent]=useState(draft.content),[version,setVersion]=useState(draft.version),[status,setStatus]=useState(''),[saving,setSaving]=useState(false)
  async function save(){setSaving(true);try{const updated=await api.updateDraft(caseId,draft.id,draft.title,content,version);setVersion(updated.version);setStatus('Saved. Review the details before sending.')}catch{setStatus('Could not save. Reload the case to check for conflicting changes; your text is still here.')}finally{setSaving(false)}}
  return <section className="draft-editor"><p className="muted">Prepared only · version {version}{draft.status==='stale'?' · case changed; review required':''}</p><textarea aria-label={`Edit ${draft.title}`} value={content} onChange={e=>setContent(e.target.value)}/><div><button disabled={saving} onClick={save}>{saving?'Saving…':'Save changes'}</button><a href={`/api/conversations/${caseId}/drafts/${draft.id}/export/docx`}>Download DOCX</a><a href={`/api/conversations/${caseId}/drafts/${draft.id}/export/pdf`}>Download PDF</a></div><p role="status">{status}</p><small>Downloads use the last saved version. Nothing is sent or filed.</small></section>
}
