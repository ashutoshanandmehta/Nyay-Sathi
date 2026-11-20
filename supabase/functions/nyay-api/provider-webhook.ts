import { readBoundedText } from './bounded-body.ts'
import { validResponseId } from './background-provider.ts'

export async function verifyCompletionWebhook(request:Request, secret:string, now=Date.now()) {
  const delivery=request.headers.get('webhook-id') || ''
  const timestamp=request.headers.get('webhook-timestamp') || ''
  const signature=request.headers.get('webhook-signature') || ''
  if(!/^[\w-]{1,160}$/.test(delivery) || !/^\d{1,12}$/.test(timestamp) ||
      Math.abs(now/1000-Number(timestamp))>300 || signature.length>1024 || !secret.startsWith('whsec_')) {
    throw new Error('Invalid webhook headers')
  }
  const raw=await readBoundedText(request,16_384)
  const key=await crypto.subtle.importKey('raw',Uint8Array.from(atob(secret.slice(6)),c=>c.charCodeAt(0)),
    {name:'HMAC', hash:'SHA-256'},false,['verify'])
  const payload=new TextEncoder().encode(delivery+'.'+timestamp+'.'+raw)
  let valid=false
  for(const value of signature.split(' ')) {
    if(!/^v1,[A-Za-z0-9+/]{43}=$/.test(value)) continue
    const mac=Uint8Array.from(atob(value.slice(3)),c=>c.charCodeAt(0))
    if(await crypto.subtle.verify('HMAC',key,mac,payload)) { valid=true; break }
  }
  if(!valid) throw new Error('Invalid webhook signature')
  const event=JSON.parse(raw)
  if(!['response.completed','response.failed','response.incomplete','response.cancelled'].includes(event.type)) return null
  if(!validResponseId(event.data?.id)) throw new Error('Invalid response reference')
  return {delivery,responseId:event.data.id}
}

