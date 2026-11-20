export async function readBoundedText(message:Request | Response, limit:number) {
  const reader=message.body?.getReader()
  const decoder=new TextDecoder('utf-8',{fatal:true})
  let bytes=0
  let raw=''
  if(!reader) throw new Error('Missing body')
  while(true) {
    const chunk=await reader.read()
    if(chunk.done) break
    bytes+=chunk.value.length
    if(bytes>limit) { await reader.cancel(); throw new Error('Body too large') }
    raw+=decoder.decode(chunk.value,{stream:true})
  }
  raw+=decoder.decode()
  return raw
}

export async function readBoundedJson(message:Request | Response, limit:number) {
  return JSON.parse(await readBoundedText(message,limit))
}
