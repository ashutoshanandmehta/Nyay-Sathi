import { completed, structured, validate, type WireResponse } from './responses-wire.ts'
// Production OpenAI Responses API adapter for Supabase Edge Runtime (Deno / Web Fetch).
// Enforces store: false, strict structured schemas, and bounded per-call timeouts.

import type { AgentAnswer, AgentReview, RepairPatch, ResearchRequest } from './contracts.ts'
import type { AiProviderPort, PrimaryStepOutput } from './handler.ts'
import { retrieveCertifiedPassages } from './knowledge.ts'

export const PRIMARY_TOOLS = [
  {
    type: 'function',
    name: 'emit_safety',
    description: 'Emit approved urgent protective guidance before full response generation when immediate physical, domestic, self-harm, medical, or active financial-fraud risk is detected.',
    parameters: {
      type: 'object',
      properties: {
        category: {
          type: 'string',
          enum: ['physical_safety', 'domestic_violence', 'self_harm', 'financial_cyber_fraud', 'medical_emergency'],
        },
      },
      required: ['category'],
      additionalProperties: false,
    },
    strict: true,
  },
  {
    type: 'function',
    name: 'research_legal_issue',
    description: 'Search certified Indian statutory and procedural propositions for material legal gaps.',
    parameters: {
      type: 'object',
      properties: {
        questions: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              query: { type: 'string' },
              material_gap: { type: 'string' },
            },
            required: ['query', 'material_gap'],
            additionalProperties: false,
          },
        },
      },
      required: ['questions'],
      additionalProperties: false,
    },
    strict: true,
  },
]

export const AGENT_ANSWER_SCHEMA = {
  type: 'json_schema',
  name: 'agent_answer',
  strict: true,
  schema: {
    type: 'object',
    properties: {
      central_question: { type: 'string' },
      risk: { type: 'string', enum: ['ordinary', 'elevated', 'urgent'] },
      case_stage: { type: 'string' },
      next_action: { type: 'string' },
      factual_issues: { type: 'array', items: { type: 'string' } },
      legal_issues: { type: 'array', items: { type: 'string' } },
      tasks: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            task_id: { type: 'string' },
            title: { type: 'string' },
            intent: {
              type: 'string',
              enum: ['information', 'legal_options', 'draft', 'summary', 'conversation', 'practice'],
            },
            domain: {
              type: 'string',
              enum: [
                'consumer',
                'financial_fraud',
                'banking',
                'criminal',
                'employment',
                'tenancy',
                'rti',
                'other_legal',
                'general',
                'unknown',
              ],
            },
            case_link: { type: 'string', enum: ['new', 'existing', 'unrelated', 'uncertain'] },
            source_segment_ids: { type: 'array', items: { type: 'string' } },
          },
          required: ['task_id', 'title', 'intent', 'domain', 'case_link', 'source_segment_ids'],
          additionalProperties: false,
        },
      },
      claims: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            claim_id: { type: 'string' },
            task_id: { type: 'string' },
            kind: {
              type: 'string',
              enum: ['quote', 'factual', 'legal', 'procedure', 'practical', 'document', 'question'],
            },
            block_type: {
              type: 'string',
              enum: [
                'direct_answer',
                'immediate_actions',
                'recommended_route',
                'evidence_checklist',
                'document',
                'alternatives',
                'question',
                'human_handoff',
              ],
            },
            grounding: {
              type: 'string',
              enum: ['reported_by_user', 'verified_legal_source', 'practical_precaution', 'requires_confirmation'],
            },
            text: { type: 'string' },
            evidence_ids: { type: 'array', items: { type: 'string' } },
            depends_on: { type: 'array', items: { type: 'string' } },
            optional: { type: 'boolean' },
            in_document: { type: 'boolean' },
          },
          required: [
            'claim_id',
            'task_id',
            'kind',
            'block_type',
            'grounding',
            'text',
            'evidence_ids',
            'depends_on',
            'optional',
            'in_document',
          ],
          additionalProperties: false,
        },
      },
      case_patches: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            patch_id: { type: 'string' },
            task_id: { type: 'string' },
            operation: {
              type: 'string',
              enum: ['fact', 'correction', 'timeline', 'event', 'party', 'location', 'remedy', 'action', 'response', 'outcome'],
            },
            payload: {
              type: 'object',
              properties: {
                key: { type: 'string' },
                value: { type: 'string' },
              },
              required: ['key', 'value'],
              additionalProperties: false,
            },
            source_refs: { type: 'array', items: { type: 'string' } },
          },
          required: ['patch_id', 'task_id', 'operation', 'payload', 'source_refs'],
          additionalProperties: false,
        },
      },
    },
    required: [
      'central_question',
      'risk',
      'case_stage',
      'next_action',
      'factual_issues',
      'legal_issues',
      'tasks',
      'claims',
      'case_patches',
    ],
    additionalProperties: false,
  },
}

export const AGENT_REVIEW_SCHEMA = {
  type: 'json_schema',
  name: 'agent_review',
  strict: true,
  schema: {
    type: 'object',
    properties: {
      claims: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            claim_id: { type: 'string' },
            support: { type: 'string', enum: ['supported', 'unsupported', 'uncertain'] },
            reason: { type: 'string' },
            requires_public_evidence: { type: 'boolean' },
          },
          required: ['claim_id', 'support', 'reason', 'requires_public_evidence'],
          additionalProperties: false,
        },
      },
      patch_verdicts: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            patch_id: { type: 'string' },
            support: { type: 'string', enum: ['supported', 'unsupported', 'uncertain'] },
            reason: { type: 'string' },
          },
          required: ['patch_id', 'support', 'reason'],
          additionalProperties: false,
        },
      },
      primary_question_answered: { type: 'boolean' },
      next_action_useful: { type: 'boolean' },
      cross_block_coherent: { type: 'boolean' },
      repair_instructions: { type: 'array', items: { type: 'string' } },
    },
    required: [
      'claims',
      'patch_verdicts',
      'primary_question_answered',
      'next_action_useful',
      'cross_block_coherent',
      'repair_instructions',
    ],
    additionalProperties: false,
  },
}

export const AGENT_REPAIR_SCHEMA = {
  type: 'json_schema',
  name: 'agent_repair',
  strict: true,
  schema: {
    type: 'object',
    properties: {
      removals: { type: 'array', items: { type: 'string' } },
      replacements: AGENT_ANSWER_SCHEMA.schema.properties.claims,
      additions: AGENT_ANSWER_SCHEMA.schema.properties.claims,
    },
    required: ['removals', 'replacements', 'additions'],
    additionalProperties: false,
  },
}

export function parsePrimary(data: WireResponse): PrimaryStepOutput {
  const output = completed(data)
  const calls = output.filter(o => o.type === 'function_call') as unknown as Array<{call_id:string;name:string;arguments:string}>
  const ids = new Set<string>()
  for (const call of calls) {
    const tool = PRIMARY_TOOLS.find(t => t.name === call.name)
    if (!tool || typeof call.call_id !== 'string' || !/^call_[a-zA-Z0-9_-]{1,150}$/.test(call.call_id) || ids.has(call.call_id) || typeof call.arguments !== 'string') throw new Error('Invalid tool call')
    ids.add(call.call_id)
    validate(JSON.parse(call.arguments), tool.parameters)
  }
  if (calls.length > 0) {
    return {
      kind: 'tool_calls',
      rawOutput: data.output || [],
      calls,
      usage: data.usage,
    }
  }
  const parsed = structured<AgentAnswer>(data, AGENT_ANSWER_SCHEMA.schema)
  return {
    kind: 'answer',
    answer: parsed,
    usage: data.usage,
  }
}

export class OpenAiResponsesProvider implements AiProviderPort {
  private chatModel: string
  private reviewModel: string
  private timeoutMs: number

  constructor(options?: { chatModel?: string; reviewModel?: string; timeoutMs?: number }) {
    this.chatModel = options?.chatModel || 'gpt-4o'
    this.reviewModel = options?.reviewModel || 'gpt-4o'
    this.timeoutMs = options?.timeoutMs || 45_000
  }

  async validateApiKey(apiKey: string): Promise<boolean> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 10_000)
    try {
      const res = await fetch('https://api.openai.com/v1/models', {
        method: 'GET',
        headers: { Authorization: `Bearer ${apiKey}` },
        signal: controller.signal,
      })
      return res.ok
    } catch {
      return false
    } finally {
      clearTimeout(timer)
    }
  }

  async generatePrimary(params: {
    apiKey: string
    items: Array<Record<string, unknown>>
    context: Record<string, unknown>
    round: number
  }): Promise<PrimaryStepOutput> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const res = await fetch('https://api.openai.com/v1/responses', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${params.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: this.chatModel,
          store: false,
          instructions:
            'You are Nyay Saathi Primary Legal Reasoning Agent for India. Ground every legal claim in supplied certified evidence_ids. Never invent URLs or statutory sections.',
          input: params.items,
          tools: PRIMARY_TOOLS,
          text: { format: AGENT_ANSWER_SCHEMA },
        }),
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(`OpenAI primary call failed with status ${res.status}`)
      }
      const data = await res.json() as WireResponse
      return parsePrimary(data)
    } finally {
      clearTimeout(timer)
    }
  }

  async reviewCandidate(params: {
    apiKey: string
    answer: AgentAnswer
    pendingClaimIds: string[]
    context: Record<string, unknown>
  }): Promise<{ review: AgentReview; usage?: { input_tokens: number; output_tokens: number; total_tokens: number } }> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const res = await fetch('https://api.openai.com/v1/responses', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${params.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: this.reviewModel,
          store: false,
          instructions:
            'You are Nyay Saathi Independent Verifier Agent. Audit each pending claim and case patch against supplied evidence_ids and flag any unsupported legal claims or cross-block contradictions.',
          input: [
            {
              role: 'user',
              content: JSON.stringify({
                answer: params.answer,
                pending_claim_ids: params.pendingClaimIds,
                context: params.context,
              }),
            },
          ],
          text: { format: AGENT_REVIEW_SCHEMA },
        }),
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(`OpenAI review call failed with status ${res.status}`)
      }
      const data = await res.json() as WireResponse
      const parsed = structured<AgentReview>(data, AGENT_REVIEW_SCHEMA.schema)
      const expected = new Set(params.pendingClaimIds)
      const validClaims: typeof parsed.claims = []
      const seen = new Set<string>()
      for (const verdict of parsed.claims || []) {
        if (expected.has(verdict.claim_id) && !seen.has(verdict.claim_id)) {
          seen.add(verdict.claim_id)
          validClaims.push(verdict)
        }
      }
      parsed.claims = validClaims
      return { review: parsed, usage: data.usage }
    } finally {
      clearTimeout(timer)
    }
  }

  async repairCandidate(params: {
    apiKey: string
    answer: AgentAnswer
    review: AgentReview
    acceptedClaimIds: string[]
    blockedClaimIds: Record<string, string>
    context: Record<string, unknown>
  }): Promise<{
    repaired: AgentAnswer | RepairPatch
    usage?: { input_tokens: number; output_tokens: number; total_tokens: number }
  }> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)
    try {
      const res = await fetch('https://api.openai.com/v1/responses', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${params.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: this.chatModel,
          store: false,
          instructions:
            'Repair only the rejected or incoherent claims using verified evidence_ids. Preserve already accepted claims unchanged.',
          input: [
            {
              role: 'user',
              content: JSON.stringify({
                answer: params.answer,
                review: params.review,
                accepted_claim_ids: params.acceptedClaimIds,
                blocked_claim_ids: params.blockedClaimIds,
                context: params.context,
              }),
            },
          ],
          text: { format: AGENT_REPAIR_SCHEMA },
        }),
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(`OpenAI repair call failed with status ${res.status}`)
      }
      const data = await res.json() as WireResponse
      const parsed = structured<RepairPatch>(data, AGENT_REPAIR_SCHEMA.schema)
      return { repaired: parsed, usage: data.usage }
    } finally {
      clearTimeout(timer)
    }
  }

  async runResearch(params: {
    request: ResearchRequest
    context: Record<string, unknown>
  }) {
    const combined = params.request.questions.map(q => q.query).join(' ')
    const retrieved = await retrieveCertifiedPassages({
      query: combined,
      jurisdiction: 'India',
      limit: 4,
    })
    return {
      status: retrieved.passages.length > 0 ? 'ok' : 'no_supporting_evidence',
      evidence: retrieved.passages,
      limitations: retrieved.passages.length > 0 ? [] : ['No matching certified proposition in local pack'],
    }
  }
}
