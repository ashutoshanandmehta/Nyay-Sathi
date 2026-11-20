// @vitest-environment node
// Package 0 Engineering Gate: Executable Runtime Feasibility Proof for Supabase Edge Functions
// Benchmarks actual CPU time (process.cpuUsage) and memory footprint (process.memoryUsage)
// against documented Supabase Edge Function limits (2,000 ms CPU per request, 256 MB memory).

import { describe, expect, it } from 'vitest'
import type { AgentAnswer } from '../../supabase/functions/nyay-api/contracts'
import { segmentMessage } from '../../supabase/functions/nyay-api/contracts'
import {
  exportEncryptedTransferBundle,
  importEncryptedTransferBundle,
  parseUnlockSecret,
  sealApiKey,
  unsealApiKey,
} from '../../supabase/functions/nyay-api/crypto'
import {
  processDocumentUpload,
  renderDocxXmlBytes,
  renderPrintablePdfBytes,
} from '../../supabase/functions/nyay-api/documents'
import type { EvidencePassage } from '../../supabase/functions/nyay-api/knowledge'
import {
  CERTIFIED_PROPOSITIONS,
  retrieveCertifiedPassages,
} from '../../supabase/functions/nyay-api/knowledge'
import {
  assembleResolutionBlocks,
  EvidenceRegistry,
  mechanicalChecks,
  propagateDependencies,
} from '../../supabase/functions/nyay-api/verification'

const EDGE_CPU_LIMIT_MS = 2_000
const EDGE_MEMORY_LIMIT_MB = 256

declare const process: {
  cpuUsage(prev?: { user: number; system: number }): { user: number; system: number }
  memoryUsage(): { heapUsed: number }
}

function measureCpuAndMemory<T>(fn: () => Promise<T>): Promise<{
  result: T
  cpuMs: number
  wallMs: number
  heapUsedMb: number
  heapDeltaMb: number
}> {
  const startCpu = process.cpuUsage()
  const startMem = process.memoryUsage().heapUsed
  const startWall = performance.now()
  return fn().then(result => {
    const cpuDiff = process.cpuUsage(startCpu)
    const endMem = process.memoryUsage().heapUsed
    const wallMs = performance.now() - startWall
    const cpuMs = (cpuDiff.user + cpuDiff.system) / 1000
    const heapUsedMb = endMem / (1024 * 1024)
    const heapDeltaMb = Math.max(0, (endMem - startMem) / (1024 * 1024))
    return { result, cpuMs, wallMs, heapUsedMb, heapDeltaMb }
  })
}

function buildSyntheticMultiPagePdf(pageCount: number): Uint8Array {
  const pages: string[] = ['%PDF-1.4']
  for (let i = 1; i <= pageCount; i++) {
    pages.push(`${i} 0 obj << /Type /Page /Contents ${i + 1000} 0 R >> endobj`)
    pages.push(
      `${i + 1000} 0 obj << /Length 220 >>\nstream\nBT /F1 11 Tf 40 720 Td (Page ${i}: Tax Invoice #INV-2026-${1000 + i} for Rs. 18,400 paid via UPI UTR 632198741230. Warranty 12 months. Grievance Officer contact listed.) Tj ET\nendstream\nendobj`
    )
  }
  pages.push('%%EOF')
  return new TextEncoder().encode(pages.join('\n'))
}

describe('Package 0 Gate: Supabase Edge Runtime Feasibility (2s CPU / 256MB memory)', () => {
  it('processes a 50-page consumer invoice PDF (security scan + SHA-256 + text extraction) well under 2s CPU and 256MB', async () => {
    const pdfBytes = buildSyntheticMultiPagePdf(50)
    const metrics = await measureCpuAndMemory(() =>
      processDocumentUpload({
        filename: 'consumer-invoice-50pages.pdf',
        mimeType: 'application/pdf',
        bytes: pdfBytes,
        maxPdfPages: 50,
      })
    )

    expect(metrics.result.extraction_status).toBe('extracted')
    expect(metrics.result.metadata.page_count).toBe(50)
    expect(metrics.result.metadata.extracted_pages).toBe(50)
    expect(metrics.result.extracted_text).toContain('INV-2026-1001')
    expect(metrics.result.extracted_text).toContain('INV-2026-1050')
    expect(metrics.result.sha256).toHaveLength(64)

    // Must use < 25% of the 2,000ms Edge CPU budget and stay well within 256MB memory
    expect(metrics.cpuMs).toBeLessThan(EDGE_CPU_LIMIT_MS * 0.25)
    expect(metrics.heapUsedMb).toBeLessThan(EDGE_MEMORY_LIMIT_MB)
  })

  it('bounds a 120-page PDF to 50 pages and explicitly records partial extraction limitations', async () => {
    const pdfBytes = buildSyntheticMultiPagePdf(120)
    const metrics = await measureCpuAndMemory(() =>
      processDocumentUpload({
        filename: 'large-record-120pages.pdf',
        mimeType: 'application/pdf',
        bytes: pdfBytes,
        maxPdfPages: 50,
      })
    )

    expect(metrics.result.extraction_status).toBe('partial')
    expect(metrics.result.metadata.page_count).toBe(120)
    expect(metrics.result.metadata.extracted_pages).toBe(50)
    expect(metrics.result.metadata.limitations).toContain('first 50 of 120 pages')
    expect(metrics.cpuMs).toBeLessThan(EDGE_CPU_LIMIT_MS * 0.25)
  })

  it('executes 700-passage retrieval, mechanical verification, dependency graph, and citation assembly in < 200ms CPU', async () => {
    // Expand corpus to 700 passages (matching 14 consumer + 607 ingested + 15 propositions + 43 official pack scale)
    const syntheticCorpus: EvidencePassage[] = [...CERTIFIED_PROPOSITIONS]
    for (let i = syntheticCorpus.length; i < 700; i++) {
      syntheticCorpus.push({
        passage_id: `pack-statute-${i}`,
        source_id: `india-code-act-${i % 45}`,
        title: `Indian Statutory Provision Pack #${i}`,
        locator: `Section ${(i % 90) + 1} of Statutory Act`,
        text: `Official provision text for section ${(i % 90) + 1} covering consumer grievance, refund timeline, procedural jurisdiction, and limitation rules in India.`,
        canonical_url: `https://www.indiacode.nic.in/handle/123456789/${1000 + i}`,
        retrieved_at: '2026-11-07T00:00:00Z',
        limitations: 'Verify state rules.',
        origin: 'official_pack',
        source_type: 'indian_official',
        jurisdiction: 'India',
        effective_date: '2020-07-20',
        origin_verified: true,
        certified_proposition: i % 10 === 0,
        domain: i % 2 === 0 ? 'consumer' : 'criminal',
        keywords: ['consumer', 'refund', 'grievance', 'section', 'limitation', 'complaint'],
      })
    }

    const message =
      'Amazon picked up my defective laptop worth ₹54,000 18 days ago, and the Grievance Officer closed my ticket without refund. What are my legal options?'
    const segments = segmentMessage(message)

    const metrics = await measureCpuAndMemory(async () => {
      const retrieved = await retrieveCertifiedPassages({
        query: message,
        domain: 'consumer',
        jurisdiction: 'India',
        limit: 8,
        customPassages: syntheticCorpus,
      })

      const registry = new EvidenceRegistry({
        current_message: message,
        passages: retrieved.passages,
      })

      const candidate: AgentAnswer = {
        central_question: 'How to escalate an unresolved ₹54,000 laptop refund after Grievance Officer closure?',
        tasks: [
          {
            task_id: 'task-1',
            title: 'Consumer refund escalation',
            intent: 'legal_options',
            domain: 'consumer',
            case_link: 'new',
            source_segment_ids: segments.map(s => s.id),
          },
        ],
        claims: [
          {
            claim_id: 'c1',
            task_id: 'task-1',
            kind: 'legal',
            block_type: 'direct_answer',
            grounding: 'verified_legal_source',
            text: 'Under Rule 4 of the Consumer Protection (E-Commerce) Rules, 2020, the Grievance Officer must acknowledge complaints within 48 hours and redress them within one month.',
            evidence_ids: ['prop-consumer-ecommerce-grievance-r4'],
          },
          {
            claim_id: 'c2',
            task_id: 'task-1',
            kind: 'procedure',
            block_type: 'recommended_route',
            grounding: 'verified_legal_source',
            text: 'Because the platform Grievance Officer closed the ticket without resolution, escalate externally to the National Consumer Helpline (1915) or file before the District Consumer Commission under Section 35 of the Consumer Protection Act, 2019.',
            evidence_ids: ['prop-consumer-nch-prelitigation', 'prop-consumer-cpa2019-district-forum-s35'],
            depends_on: ['c1'],
          },
          {
            claim_id: 'c3',
            task_id: 'task-1',
            kind: 'practical',
            block_type: 'evidence_checklist',
            grounding: 'practical_precaution',
            text: '1. Preserve the pickup AWB confirmation.\n2. Save the closed Grievance Officer ticket transcript and original tax invoice.',
            evidence_ids: [`segment:${segments[0].id}`],
          },
        ],
      }

      const checked = mechanicalChecks(candidate, registry)
      const accepted = propagateDependencies(candidate, {
        ...checked.approved,
        c1: 'independent_semantic_review',
        c2: 'independent_semantic_review',
      })

      return assembleResolutionBlocks({
        answer: candidate,
        accepted,
        registry,
        language: 'en',
      })
    })

    expect(metrics.result.publicationStatus).toBe('supported')
    expect(metrics.result.sources).toHaveLength(3)
    expect(metrics.result.content).toContain('[1](#cite-1)')
    expect(metrics.result.content).toContain('[2](#cite-2)[3](#cite-3)')
    expect(metrics.cpuMs).toBeLessThan(200)
    expect(metrics.heapUsedMb).toBeLessThan(EDGE_MEMORY_LIMIT_MB)
  })

  it('executes WebCrypto AES-256-GCM BYOK sealing, transfer bundle encryption, and EN/HI PDF+DOCX exports within limits', async () => {
    const metrics = await measureCpuAndMemory(async () => {
      const unlockHeader = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0123456789_-'
      const unlock = parseUnlockSecret(unlockHeader)!
      const ownerId = '11111111-1111-4111-8111-111111111111'
      const sealed = await sealApiKey('sk-proj-test1234567890abcdefghijkl', unlock, ownerId, 'master-secret')
      const unsealed = await unsealApiKey(sealed, unlock, ownerId, 'master-secret')

      const hindiText =
        'शिकायत का विवरण: मैंने ₹18,400 का भुगतान UPI द्वारा किया लेकिन सामान खराब निकला। उपभोक्ता संरक्षण अधिनियम, 2019 के अंतर्गत रिफंड की मांग।'
      const pdfBytes = renderPrintablePdfBytes('Nyay Saathi Case Pack / न्याय साथी', hindiText)
      const docxBytes = renderDocxXmlBytes('Nyay Saathi Case Pack / न्याय साथी', hindiText)

      const bundle = await exportEncryptedTransferBundle(
        { title: 'Hindi Refund Case', notes: hindiText },
        'correct-horse-battery-staple'
      )
      const restored = await importEncryptedTransferBundle(
        bundle as unknown as Record<string, unknown>,
        'correct-horse-battery-staple'
      )

      return { unsealed, pdfLen: pdfBytes.length, docxLen: docxBytes.length, restored }
    })

    expect(metrics.result.unsealed).toBe('sk-proj-test1234567890abcdefghijkl')
    expect(metrics.result.pdfLen).toBeGreaterThan(200)
    expect(metrics.result.docxLen).toBeGreaterThan(200)
    expect(metrics.result.restored.title).toBe('Hindi Refund Case')
    expect(metrics.cpuMs).toBeLessThan(EDGE_CPU_LIMIT_MS * 0.5)
    expect(metrics.heapUsedMb).toBeLessThan(EDGE_MEMORY_LIMIT_MB)
  })
})
