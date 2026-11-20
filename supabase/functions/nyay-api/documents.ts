// Runtime-compatible upload security gate, bounded PDF/text extraction, prompt-injection tagging,
// lawyer escalation bundle builder, and case/draft exporters for Supabase Edge Functions.

import type { CaseMemoryModel } from './contracts.ts'
import { sha256Hex } from './crypto.ts'

const decoder = new TextDecoder('utf-8', { fatal: false })
const latin1Decoder = new TextDecoder('latin1')
const encoder = new TextEncoder()

const PROMPT_INJECTION_RE =
  /\b(?:ignore\s+(?:all\s+)?(?:previous|prior|earlier)\s+instructions?|system\s+prompt|you\s+are\s+now\s+a|disregard\s+(?:all\s+)?rules|override\s+security|act\s+as\s+system)\b/i

const DANGEROUS_PDF_TOKENS_RE = /\/(?:JavaScript|JS|Launch|RichMedia|SubmitForm|ImportData|AA)\b/

export interface ProcessedUpload {
  filename: string
  mime_type: string
  byte_length: number
  sha256: string
  extraction_status: 'extracted' | 'partial' | 'ocr_required'
  extracted_text: string
  metadata: {
    page_count?: number
    extracted_pages?: number
    pdf_engine?: string
    embedded_instructions_untrusted: boolean
    security_scan: {
      passed: boolean
      prompt_injection_detected: boolean
    }
    limitations?: string
  }
}

function isDisguisedExecutable(bytes: Uint8Array): string | null {
  if (bytes.length >= 2 && bytes[0] === 0x4d && bytes[1] === 0x5a) {
    return 'Executable PE/MZ binary rejected'
  }
  if (bytes.length >= 4 && bytes[0] === 0x7f && bytes[1] === 0x45 && bytes[2] === 0x4c && bytes[3] === 0x46) {
    return 'Executable ELF binary rejected'
  }
  if (
    bytes.length >= 4 &&
    ((bytes[0] === 0xfe && bytes[1] === 0xed && bytes[2] === 0xfa && (bytes[3] === 0xce || bytes[3] === 0xcf)) ||
      (bytes[0] === 0xcf && bytes[1] === 0xfa && bytes[2] === 0xed && bytes[3] === 0xfe) ||
      (bytes[0] === 0xca && bytes[1] === 0xfe && bytes[2] === 0xba && bytes[3] === 0xbe))
  ) {
    return 'Executable Mach-O binary rejected'
  }
  if (bytes.length >= 2 && bytes[0] === 0x23 && bytes[1] === 0x21) {
    return 'Executable shell script rejected'
  }
  return null
}

function unescapePdfLiteral(raw: string): string {
  return raw
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\r')
    .replace(/\\t/g, '\t')
    .replace(/\\\(/g, '(')
    .replace(/\\\)/g, ')')
    .replace(/\\\\/g, '\\')
    .replace(/\\([0-7]{1,3})/g, (_, oct) => String.fromCharCode(parseInt(oct, 8)))
}

function decodePdfHexLiteral(hexRaw: string): string {
  const cleaned = hexRaw.replace(/\s+/g, '')
  if (!cleaned) return ''
  const padded = cleaned.length % 2 === 1 ? `${cleaned}0` : cleaned
  const bytes = new Uint8Array(padded.length / 2)
  for (let i = 0; i < padded.length; i += 2) {
    bytes[i / 2] = parseInt(padded.slice(i, i + 2), 16) || 0
  }
  // UTF-16BE BOM (0xFE 0xFF)
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    let out = ''
    for (let i = 2; i + 1 < bytes.length; i += 2) {
      const code = (bytes[i] << 8) | bytes[i + 1]
      if (code >= 0x20 || code === 0x0a || code === 0x09) out += String.fromCharCode(code)
    }
    return out.trim()
  }
  return decoder.decode(bytes).replace(/\0/g, '').trim()
}

function extractTextOperatorsFromStream(content: string, maxLiterals: number, chunks: string[], currentCount: { count: number }): void {
  const textOperatorRe =
    /\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*(?:Tj|')|<([0-9A-Fa-f\s]+)>\s*(?:Tj|')|\[((?:[^[\]\\]|\\.)*)\]\s*TJ/g
  let match: RegExpExecArray | null
  while ((match = textOperatorRe.exec(content)) !== null && currentCount.count < maxLiterals) {
    currentCount.count++
    if (match[1] !== undefined) {
      const cleaned = unescapePdfLiteral(match[1]).trim()
      if (cleaned) chunks.push(cleaned)
    } else if (match[2] !== undefined) {
      const decodedHex = decodePdfHexLiteral(match[2])
      if (decodedHex) chunks.push(decodedHex)
    } else if (match[3] !== undefined) {
      const innerRe = /\(([^()\\]*(?:\\.[^()\\]*)*)\)|<([0-9A-Fa-f\s]+)>/g
      let inner: RegExpExecArray | null
      const lineParts: string[] = []
      while ((inner = innerRe.exec(match[3])) !== null) {
        if (inner[1] !== undefined) lineParts.push(unescapePdfLiteral(inner[1]))
        else if (inner[2] !== undefined) lineParts.push(decodePdfHexLiteral(inner[2]))
      }
      const joined = lineParts.join('').trim()
      if (joined) chunks.push(joined)
    }
  }
}

async function inflateFlateStreamBounded(compressed: Uint8Array, maxOutputBytes = 512 * 1024): Promise<string | null> {
  if (typeof DecompressionStream === 'undefined' || compressed.length === 0) return null
  for (const format of ['deflate', 'deflate-raw'] as const) {
    try {
      const ds = new DecompressionStream(format)
      const writer = ds.writable.getWriter()
      const writePromise = writer.write(compressed as BufferSource).then(() => writer.close()).catch(() => {})
      const reader = ds.readable.getReader()
      const outChunks: Uint8Array[] = []
      let total = 0
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        if (value) {
          total += value.byteLength
          if (total > maxOutputBytes) {
            await reader.cancel().catch(() => {})
            break
          }
          outChunks.push(value)
        }
      }
      await writePromise
      if (outChunks.length > 0) {
        const merged = new Uint8Array(total)
        let offset = 0
        for (const c of outChunks) {
          merged.set(c, offset)
          offset += c.byteLength
        }
        return bytesToIdentityLatin1(merged)
      }
    } catch {
      // Try next format
    }
  }
  return null
}

function bytesToIdentityLatin1(bytes: Uint8Array): string {
  const chunkSize = 0x8000
  let out = ''
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const sub = bytes.subarray(i, Math.min(i + chunkSize, bytes.length))
    out += String.fromCharCode(...sub)
  }
  return out
}

export async function extractBoundedPdfText(
  bytes: Uint8Array,
  maxPages = 50
): Promise<{ text: string; pageCount: number; extractedPages: number; limitations?: string }> {
  const raw = bytesToIdentityLatin1(bytes)
  if (!raw.startsWith('%PDF-')) {
    throw new Error('Malformed PDF header')
  }
  if (DANGEROUS_PDF_TOKENS_RE.test(raw)) {
    throw new Error('PDF contains prohibited active content (/JavaScript or /Launch action)')
  }

  // Count page objects boundedly
  const pageMatches = raw.match(/\/Type\s*\/Page\b(?!s)/g)
  const pageCount = Math.max(1, pageMatches ? pageMatches.length : 1)
  const extractedPages = Math.min(pageCount, Math.max(1, maxPages))

  const chunks: string[] = []
  const maxLiterals = extractedPages * 250
  const counter = { count: 0 }

  // 1. Extract uncompressed literal and hex strings directly
  extractTextOperatorsFromStream(raw, maxLiterals, chunks, counter)

  // 2. Boundedly inflate /FlateDecode streams if present and within literal budget
  if (raw.includes('/FlateDecode') && counter.count < maxLiterals) {
    const flateRe = /<<[\s\S]*?\/Filter\s*(?:\[\s*)?\/FlateDecode\b[\s\S]*?>>\s*stream(?:\r\n|\n)([\s\S]*?)endstream/g
    let flateMatch: RegExpExecArray | null
    let streamCount = 0
    const maxStreams = extractedPages * 2
    while ((flateMatch = flateRe.exec(raw)) !== null && streamCount < maxStreams && counter.count < maxLiterals) {
      streamCount++
      let bodyLatin1 = flateMatch[1]
      if (bodyLatin1.endsWith('\r\n')) bodyLatin1 = bodyLatin1.slice(0, -2)
      else if (bodyLatin1.endsWith('\n') || bodyLatin1.endsWith('\r')) bodyLatin1 = bodyLatin1.slice(0, -1)
      const streamBytes = new Uint8Array(bodyLatin1.length)
      for (let i = 0; i < bodyLatin1.length; i++) {
        streamBytes[i] = bodyLatin1.charCodeAt(i) & 0xff
      }
      const inflated = await inflateFlateStreamBounded(streamBytes)
      if (inflated) {
        if (DANGEROUS_PDF_TOKENS_RE.test(inflated)) {
          throw new Error('PDF contains prohibited active content (/JavaScript or /Launch action)')
        }
        extractTextOperatorsFromStream(inflated, maxLiterals, chunks, counter)
      }
    }
  }

  const limitations =
    pageCount > extractedPages
      ? `Extracted first ${extractedPages} of ${pageCount} pages within runtime bounds`
      : undefined

  return {
    text: chunks.join(' ').slice(0, 100_000),
    pageCount,
    extractedPages,
    limitations,
  }
}

export async function processDocumentUpload(options: {
  filename: string
  mimeType: string
  bytes: Uint8Array
  maxUploadBytes?: number
  maxPdfPages?: number
}): Promise<ProcessedUpload> {
  const maxBytes = options.maxUploadBytes ?? 10 * 1024 * 1024
  const maxPages = options.maxPdfPages ?? 50

  if (options.bytes.length === 0) {
    throw new Error('Empty file upload rejected')
  }
  if (options.bytes.length > maxBytes) {
    throw new Error(`File exceeds maximum upload limit of ${maxBytes} bytes`)
  }

  const execErr = isDisguisedExecutable(options.bytes)
  if (execErr) {
    throw new Error(execErr)
  }

  const sha256 = await sha256Hex(options.bytes)
  const lowerName = (options.filename || 'document').toLowerCase()
  const mime = (options.mimeType || 'application/octet-stream').toLowerCase()
  const isPdf = mime === 'application/pdf' || lowerName.endsWith('.pdf')
  const isImage = mime.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(lowerName)
  const isText =
    mime.startsWith('text/') ||
    mime === 'application/json' ||
    /\.(txt|md|csv|json|log)$/i.test(lowerName)

  if (!isPdf && !isImage && !isText) {
    throw new Error(`Unsupported file format: ${options.mimeType || lowerName}`)
  }

  if (isPdf) {
    const extracted = await extractBoundedPdfText(options.bytes, maxPages)
    const injection = PROMPT_INJECTION_RE.test(extracted.text)
    const status =
      !extracted.text.trim()
        ? 'ocr_required'
        : extracted.pageCount > extracted.extractedPages
          ? 'partial'
          : 'extracted'
    return {
      filename: options.filename,
      mime_type: 'application/pdf',
      byte_length: options.bytes.length,
      sha256,
      extraction_status: status,
      extracted_text: extracted.text,
      metadata: {
        page_count: extracted.pageCount,
        extracted_pages: extracted.extractedPages,
        pdf_engine: 'edge-stream-pdf-v1',
        embedded_instructions_untrusted: injection,
        security_scan: {
          passed: true,
          prompt_injection_detected: injection,
        },
        ...(extracted.limitations ? { limitations: extracted.limitations } : {}),
      },
    }
  }

  if (isImage) {
    return {
      filename: options.filename,
      mime_type: mime.startsWith('image/') ? mime : 'image/png',
      byte_length: options.bytes.length,
      sha256,
      extraction_status: 'ocr_required',
      extracted_text: '',
      metadata: {
        embedded_instructions_untrusted: false,
        security_scan: {
          passed: true,
          prompt_injection_detected: false,
        },
        limitations:
          'Image hash recorded. Client/Android OCR or manual text review required so untrusted extracted text stays linked to original SHA-256.',
      },
    }
  }

  const text = decoder.decode(options.bytes).slice(0, 100_000)
  const injection = PROMPT_INJECTION_RE.test(text)
  return {
    filename: options.filename,
    mime_type: mime.startsWith('text/') ? mime : 'text/plain',
    byte_length: options.bytes.length,
    sha256,
    extraction_status: 'extracted',
    extracted_text: text,
    metadata: {
      embedded_instructions_untrusted: injection,
      security_scan: {
        passed: true,
        prompt_injection_detected: injection,
      },
    },
  }
}

export function buildEscalationBundle(options: {
  conversation: Record<string, unknown>
  memory: CaseMemoryModel
  summary: string
  messages: Array<Record<string, unknown>>
  attachments: Array<Record<string, unknown>>
  drafts: Array<Record<string, unknown>>
  safetyMessages: Array<Record<string, unknown>>
  userActions: Array<Record<string, unknown>>
  submissionSteps: Array<Record<string, unknown>>
}): Record<string, unknown> {
  const formatDateOnly = (ts: unknown): string => {
    const str = String(ts || '')
    const m = str.match(/^\d{4}-\d{2}-\d{2}/)
    return m ? m[0] : 'Date not stated'
  }

  const reasons: string[] = []
  if (options.memory.domain === 'criminal') {
    reasons.push('Criminal matter: personal liberty may be at stake (arrest, custody or bail).')
  }
  if (options.safetyMessages.length > 0) {
    reasons.push('Safety guidance was shown during this conversation.')
  }
  if ((options.memory.contradictions || []).length > 0) {
    reasons.push('Material factual contradictions require human verification against originals.')
  }

  const assistantMsgs = options.messages.filter(m => m.role === 'assistant' && m.status === 'complete')
  const partialTurns = assistantMsgs.filter(
    m => ((m.metadata || {}) as Record<string, unknown>).publication_status === 'partial'
  )
  if (partialTurns.length > 0) {
    reasons.push('At least one legal question had partial source verification and benefits from counsel review.')
  }

  const consistentFacts: Array<Record<string, unknown>> = []
  const uncertainFacts: Array<Record<string, unknown>> = []
  for (const [key, item] of Object.entries(options.memory.facts || {})) {
    const statusVal = item.status || 'user_allegation'
    const entry = {
      key,
      value: item.value,
      status: statusVal,
      provenance: item.provenance || [],
      previous_values: item.previous_values || [],
    }
    if (statusVal === 'assistant_inference' || (item.previous_values && item.previous_values.length > 0)) {
      uncertainFacts.push(entry)
    } else {
      consistentFacts.push(entry)
    }
  }

  const chronology: Array<Record<string, unknown>> = []
  for (const rawEv of options.memory.events || []) {
    const ts = String(rawEv.date || '')
    chronology.push({
      date: formatDateOnly(ts),
      timestamp: ts,
      kind: 'reported_event',
      event_type: 'reported_event',
      summary: String(rawEv.description || ''),
      status: 'user_reported',
    })
  }
  for (const msg of options.messages) {
    const ts = String(msg.created_at || '')
    const kind = msg.role === 'user' ? 'user_statement' : 'verified_guidance'
    chronology.push({
      date: formatDateOnly(ts),
      timestamp: ts,
      kind,
      event_type: kind,
      summary: String(msg.content || '').slice(0, 240),
      status: String(msg.status || 'complete'),
    })
  }
  for (const act of options.userActions) {
    const ts = String(act.occurred_at || act.created_at || '')
    chronology.push({
      date: formatDateOnly(ts),
      timestamp: ts,
      kind: 'user_tracked_action',
      event_type: 'user_reported_action',
      summary: `${act.title} (${act.status})`,
      status: String(act.status || 'completed'),
    })
  }
  for (const sub of options.submissionSteps) {
    const ts = String(sub.created_at || '')
    const kind = `submission_${sub.step}`
    chronology.push({
      date: formatDateOnly(ts),
      timestamp: ts,
      kind,
      event_type: kind,
      summary: `${sub.target_channel}: ${sub.step}${sub.receipt_reference ? ` [Ref: ${sub.receipt_reference}]` : ''}`,
      status: String(sub.step),
    })
  }

  const publishedSources = new Map<string, Record<string, unknown>>()
  const structuredFindings: Array<Record<string, unknown>> = []
  const legalIssuesFromTurns: string[] = []
  const factualIssuesFromTurns: string[] = []
  const limitationNotes: string[] = []

  for (const msg of assistantMsgs.slice(-5)) {
    const meta = (msg.metadata || {}) as Record<string, unknown>
    for (const li of (meta.legal_issues as string[] | undefined) || []) {
      if (li && !legalIssuesFromTurns.includes(li)) legalIssuesFromTurns.push(li)
    }
    for (const fi of (meta.factual_issues as string[] | undefined) || []) {
      if (fi && !factualIssuesFromTurns.includes(fi)) factualIssuesFromTurns.push(fi)
    }
    for (const src of (meta.sources as Array<Record<string, unknown>> | undefined) || []) {
      const pid = String(src.passage_id || src.source_id || '')
      if (pid && !publishedSources.has(pid)) {
        publishedSources.set(pid, {
          source_id: src.source_id || pid,
          passage_id: pid,
          title: src.title || 'Official Source',
          locator: src.locator || '',
          canonical_url: src.canonical_url || '',
          verification_status: src.verification_status || 'editor_certified',
          effective_date: src.effective_date || null,
          limitations: src.limitations || '',
        })
      }
    }
    for (const blk of (meta.resolution_blocks as Array<Record<string, unknown>> | undefined) || []) {
      if (blk.block_type === 'limitation' && typeof blk.content === 'string') {
        limitationNotes.push(blk.content)
      }
      if (['direct_answer', 'recommended_route', 'alternatives'].includes(String(blk.block_type || ''))) {
        structuredFindings.push({
          message_id: msg.id,
          block_type: blk.block_type,
          title: blk.title,
          content: blk.content,
          grounding: blk.grounding,
          source_ids: blk.source_ids || [],
        })
      }
    }
  }

  const evidenceIndex = options.attachments.map(a => ({
    id: a.id,
    attachment_id: a.id,
    filename: a.filename,
    mime_type: a.mime_type,
    size_bytes: a.byte_length ?? a.size ?? 0,
    sha256: a.sha256,
    extraction_status: a.extraction_status,
    consent_status: a.consent_status || 'consented',
    uploaded_at: a.created_at,
  }))

  const preparedDrafts = options.drafts.map(d => ({
    id: d.id,
    draft_id: d.id,
    title: d.title,
    version: d.version,
    status: d.status,
    case_version: d.case_version,
    content: d.content,
    updated_at: d.updated_at,
  }))

  const statedFacts = [...consistentFacts, ...uncertainFacts].map(
    f =>
      `${String(f.key).replace(/_/g, ' ').replace(/^./, c => c.toUpperCase())}: ${f.value}${
        uncertainFacts.includes(f) ? ' (unconfirmed)' : ''
      }`
  )

  const questionsForCounsel = [
    ...(options.memory.questions_for_legal_review || []),
    ...(options.memory.legal_issues_for_review || []),
    ...legalIssuesFromTurns,
  ].slice(0, 10)

  const factsToEstablish = [...(options.memory.unknowns || []), ...factualIssuesFromTurns].slice(0, 10)
  const caseTitle = String(options.conversation.title || 'Legal Escalation Brief')
  const autonomyNotice =
    'Prepared by Nyay Saathi for user-authorized review or licensed-advocate consultation. Does not constitute legal representation or proof of official filing.'

  return {
    bundle_version: 'escalation-bundle-v2',
    generated_at: new Date().toISOString(),
    case_id: options.conversation.case_id || options.conversation.id,
    conversation_id: options.conversation.id,
    case_title: caseTitle,
    title: caseTitle,
    language: options.conversation.language || 'en',
    case_version: options.memory.version,
    domain: options.memory.domain,
    case_stage: options.memory.case_stage,
    escalation_recommended: reasons.length > 0,
    escalation_reasons: reasons.length > 0 ? reasons : ['Requested by the client for legal review.'],
    executive_summary:
      options.summary ||
      `Prepared case dossier for ${caseTitle} (${Object.keys(options.memory.facts).length} recorded facts, ${options.attachments.length} evidence items).`,
    facts: options.memory.facts,
    facts_partition: {
      reported_and_consistent: consistentFacts,
      uncertain_or_disputed: uncertainFacts,
      contradictions: options.memory.contradictions || [],
    },
    stated_facts: statedFacts,
    writing: 'plain',
    evidence_index: evidenceIndex,
    evidence_register: evidenceIndex,
    questions_for_counsel: questionsForCounsel,
    facts_to_establish: factsToEstablish,
    not_confirmed: limitationNotes.slice(0, 6),
    generated_drafts: preparedDrafts,
    prepared_drafts: preparedDrafts,
    user_actions: options.userActions,
    submission_trail: options.submissionSteps,
    chronology: chronology.length
      ? chronology
      : [
          {
            date: formatDateOnly(new Date().toISOString()),
            timestamp: new Date().toISOString(),
            kind: 'case_initialized',
            event_type: 'case_initialized',
            summary: 'Case opened',
            status: 'complete',
          },
        ],
    source_backed_analysis: {
      findings: structuredFindings.slice(-8),
      verified_sources: Array.from(publishedSources.values()),
      contains_hidden_model_reasoning: false,
      separation_rule:
        'User allegations, unverified document statements, and verified statutory propositions are kept separate.',
    },
    autonomy_notice: autonomyNotice,
    disclaimer: autonomyNotice,
  }
}

export function renderPrintablePdfBytes(title: string, bodyText: string): Uint8Array {
  const safeLines = [title, '', ...bodyText.split('\n')]
    .slice(0, 120)
    .map(l =>
      l
        .replace(/\\/g, '\\\\')
        .replace(/\(/g, '\\(')
        .replace(/\)/g, '\\)')
        .slice(0, 110)
    )

  const streamLines = ['BT', '/F1 11 Tf', '50 760 Td', '14 TL']
  for (const line of safeLines) {
    streamLines.push(`(${line}) Tj T*`)
  }
  streamLines.push('ET')
  const streamContent = streamLines.join('\n')
  const streamByteLength = encoder.encode(streamContent).byteLength

  const objects = [
    '1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj',
    '2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj',
    '3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj',
    `4 0 obj << /Length ${streamByteLength} >>\nstream\n${streamContent}\nendstream\nendobj`,
    '5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj',
  ]

  const header = '%PDF-1.4\n'
  const offsets: number[] = []
  let currentOffset = encoder.encode(header).byteLength
  const bodyParts: string[] = [header]

  for (const obj of objects) {
    offsets.push(currentOffset)
    const objWithNewline = `${obj}\n`
    bodyParts.push(objWithNewline)
    currentOffset += encoder.encode(objWithNewline).byteLength
  }

  const xrefOffset = currentOffset
  const xrefLines = [
    'xref',
    `0 ${objects.length + 1}`,
    '0000000000 65535 f ',
    ...offsets.map(off => `${String(off).padStart(10, '0')} 00000 n `),
    `trailer << /Size ${objects.length + 1} /Root 1 0 R >>`,
    'startxref',
    String(xrefOffset),
    '%%EOF',
  ]

  return encoder.encode(bodyParts.join('') + xrefLines.join('\n'))
}

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff
  for (let i = 0; i < bytes.length; i++) {
    c ^= bytes[i]
    for (let k = 0; k < 8; k++) {
      c = (c & 1) !== 0 ? (c >>> 1) ^ 0xedb88320 : c >>> 1
    }
  }
  return (c ^ 0xffffffff) >>> 0
}

function buildStoreZip(files: Array<{ name: string; data: Uint8Array }>): Uint8Array {
  const localParts: Uint8Array[] = []
  const centralParts: Uint8Array[] = []
  let offset = 0

  for (const file of files) {
    const nameBytes = encoder.encode(file.name)
    const crc = crc32(file.data)
    const size = file.data.byteLength

    const localHeader = new Uint8Array(30 + nameBytes.byteLength)
    const lv = new DataView(localHeader.buffer)
    lv.setUint32(0, 0x04034b50, true)
    lv.setUint16(4, 20, true)
    lv.setUint16(6, 0x0800, true) // UTF-8 filename flag
    lv.setUint16(8, 0, true) // Store (no compression)
    lv.setUint16(10, 0, true)
    lv.setUint16(12, 0, true)
    lv.setUint32(14, crc, true)
    lv.setUint32(18, size, true)
    lv.setUint32(22, size, true)
    lv.setUint16(26, nameBytes.byteLength, true)
    lv.setUint16(28, 0, true)
    localHeader.set(nameBytes, 30)

    const centralHeader = new Uint8Array(46 + nameBytes.byteLength)
    const cv = new DataView(centralHeader.buffer)
    cv.setUint32(0, 0x02014b50, true)
    cv.setUint16(4, 20, true)
    cv.setUint16(6, 20, true)
    cv.setUint16(8, 0x0800, true)
    cv.setUint16(10, 0, true)
    cv.setUint16(12, 0, true)
    cv.setUint16(14, 0, true)
    cv.setUint32(16, crc, true)
    cv.setUint32(20, size, true)
    cv.setUint32(24, size, true)
    cv.setUint16(28, nameBytes.byteLength, true)
    cv.setUint16(30, 0, true)
    cv.setUint16(32, 0, true)
    cv.setUint16(34, 0, true)
    cv.setUint16(36, 0, true)
    cv.setUint32(38, 0, true)
    cv.setUint32(42, offset, true)
    centralHeader.set(nameBytes, 46)

    localParts.push(localHeader, file.data)
    centralParts.push(centralHeader)
    offset += localHeader.byteLength + size
  }

  const centralSize = centralParts.reduce((acc, p) => acc + p.byteLength, 0)
  const eocd = new Uint8Array(22)
  const ev = new DataView(eocd.buffer)
  ev.setUint32(0, 0x06054b50, true)
  ev.setUint16(4, 0, true)
  ev.setUint16(6, 0, true)
  ev.setUint16(8, files.length, true)
  ev.setUint16(10, files.length, true)
  ev.setUint32(12, centralSize, true)
  ev.setUint32(16, offset, true)
  ev.setUint16(20, 0, true)

  const totalSize = offset + centralSize + eocd.byteLength
  const out = new Uint8Array(totalSize)
  let pos = 0
  for (const part of [...localParts, ...centralParts, eocd]) {
    out.set(part, pos)
    pos += part.byteLength
  }
  return out
}

export function renderDocxXmlBytes(title: string, bodyText: string): Uint8Array {
  const escapeXml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  const paragraphs = [title, ...bodyText.split('\n')]
    .map(line => `<w:p><w:r><w:t>${escapeXml(line)}</w:t></w:r></w:p>`)
    .join('')
  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>${paragraphs}</w:body>
</w:document>`

  const contentTypesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>`

  const relsXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`

  return buildStoreZip([
    { name: '[Content_Types].xml', data: encoder.encode(contentTypesXml) },
    { name: '_rels/.rels', data: encoder.encode(relsXml) },
    { name: 'word/document.xml', data: encoder.encode(documentXml) },
  ])
}
