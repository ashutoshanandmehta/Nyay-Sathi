// Prices checked against the official model pages on 2026-11-20.
// Estimates are USD at Standard processing, not a provider billing receipt.
export const RUNTIME_MODELS = {
  'gpt-6.2-sol': {input:2,cached:0.1,output:10},
  'gpt-6.2-astra': {input:8,cached:0.4,output:40},
} as const
export interface RuntimeConfig {
  model:keyof typeof RUNTIME_MODELS
  reasoning:'low'|'medium'|'high'
  maxOutputTokens:number
}
export const MAX_SUBMISSIONS=6
export const MAX_REQUEST_BYTES=64_000
// UTF-8 byte bound plus conservative framing/tool overhead; enforce the body bound too.
export const MAX_INPUT_TOKENS=MAX_REQUEST_BYTES+8192
export const DEFAULT_RUNTIME:RuntimeConfig={model:'gpt-6.2-sol',reasoning:'low',maxOutputTokens:4096}
export function runtimeConfig(values:Partial<Record<'model'|'reasoning'|'maxOutputTokens',unknown>>={}):RuntimeConfig {
  const config={...DEFAULT_RUNTIME,...values}
  if(!Object.hasOwn(RUNTIME_MODELS,String(config.model)) ||
    !['low','medium','high'].includes(String(config.reasoning)) ||
    !Number.isInteger(config.maxOutputTokens) || Number(config.maxOutputTokens)<1024 || Number(config.maxOutputTokens)>8192) {
    throw new Error('Invalid runtime model configuration')
  }
  return config as RuntimeConfig
}
export function callReserve(config:RuntimeConfig):number {
  const price=RUNTIME_MODELS[config.model]
  return Math.ceil((MAX_INPUT_TOKENS*price.input*1.25+config.maxOutputTokens*price.output)*1000)/1e9
}
export function runReserve(config:RuntimeConfig):number {return Math.round(callReserve(config)*MAX_SUBMISSIONS*1e9)/1e9}
export interface TokenUsage {input_tokens:number;output_tokens:number;total_tokens:number;
  input_tokens_details?:{cached_tokens?:number;cache_write_tokens?:number;
    cache_write_tokens_details?:{ttl_30m_tokens?:number;ttl_12h_tokens?:number}};
  output_tokens_details?:{reasoning_tokens?:number}}
export function usageCost(config:RuntimeConfig,usage:TokenUsage):number {
  const cached=usage.input_tokens_details?.cached_tokens || 0
  const reasoning=usage.output_tokens_details?.reasoning_tokens || 0
  const writes=usage.input_tokens_details?.cache_write_tokens || 0
  // Older/malformed usage without write details is priced conservatively until reconciled.
  const unclassified=usage.input_tokens_details?.cache_write_tokens==null?usage.input_tokens-cached:0
  const details=usage.input_tokens_details?.cache_write_tokens_details
  const longWrites=details?.ttl_12h_tokens || 0
  const shortWrites=details?.ttl_30m_tokens ?? (writes-longWrites)
  if(![usage.input_tokens,usage.output_tokens,cached,reasoning,writes,longWrites,shortWrites].every(n=>Number.isSafeInteger(n)&&n>=0) ||
      cached+writes>usage.input_tokens || shortWrites+longWrites!==writes || reasoning>usage.output_tokens) throw new Error('Invalid provider usage')
  const price=RUNTIME_MODELS[config.model]
  return Math.ceil(((usage.input_tokens-cached-writes)*price.input+cached*price.cached+
    shortWrites*price.input*1.25+longWrites*price.input*2.5+unclassified*price.input*0.25+
    usage.output_tokens*price.output)*1000)/1e9
}
