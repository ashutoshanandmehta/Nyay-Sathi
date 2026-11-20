// Runtime validation uses the same strict schema sent to the provider.
export type Schema = {type?:string; properties?:Record<string,Schema | undefined>; required?:string[]; additionalProperties?:boolean; items?:Schema; enum?:readonly unknown[]}
export function validate(value:unknown, schema:Schema, path='output'): void {
  if(schema.enum && !schema.enum.includes(value)) throw new Error(`${path}: invalid enum`)
  if(schema.type==='object') {
    if(!value || typeof value!=='object' || Array.isArray(value)) throw new Error(`${path}: expected object`)
    const obj=value as Record<string,unknown>
    for(const key of schema.required || []) if(!(key in obj)) throw new Error(`${path}.${key}: required`)
    for(const [key,item] of Object.entries(obj)) {
      if(schema.properties?.[key]) validate(item,schema.properties[key],`${path}.${key}`)
      else if(schema.additionalProperties===false) throw new Error(`${path}.${key}: unknown property`)
    }
  } else if(schema.type==='array') {
    if(!Array.isArray(value) || value.length>256) throw new Error(`${path}: invalid array`)
    for(const item of value) validate(item,schema.items || {},path+'[]')
  } else if(schema.type && typeof value!==schema.type) throw new Error(`${path}: expected ${schema.type}`)
}
export type WireResponse = {id?:string; metadata?:Record<string,string>; status?:string; output?:Array<Record<string,unknown>>; usage?:import('./runtime-config').TokenUsage}
export function completed(data:WireResponse): Array<Record<string,unknown>> {
  if(data.status!=='completed' || !Array.isArray(data.output)) throw new Error(`Provider response not completed: ${data.status}`)
  for(const item of data.output) {
    if(item.type==='message') {
      if(item.status && item.status!=='completed') throw new Error('Incomplete message')
      for(const part of (item.content || []) as Array<Record<string,unknown>>) if(part.type==='refusal') throw new Error('Provider refusal')
    }
  }
  return data.output
}
export function structured<T>(data:WireResponse,schema:Schema):T {
  const output=completed(data)
  if(output.some(x=>x.type==='function_call')) throw new Error('Unexpected tool call')
  const text=output.filter(x=>x.type==='message' && x.role==='assistant').flatMap(x=>(x.content || []) as Array<Record<string,unknown>>).filter(x=>x.type==='output_text').map(x=>x.text).join('')
  if(!text || text.length>1_000_000) throw new Error('Missing or oversized response text')
  const value:unknown=JSON.parse(text); validate(value,schema); return value as T
}
