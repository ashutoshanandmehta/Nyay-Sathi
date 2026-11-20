// Real hybrid semantic + lexical Indian legal retrieval behind retrieval-port.ts.
// Compatible with Deno 2 (Supabase Edge Functions) and Node/Vitest.

import { LEGAL_CORPUS_BUNDLE } from './legal-corpus-data.ts'
import type { RetrievalRequest, RetrievalResult, RetrievedPassage, RetrieveEvidence } from './retrieval-port.ts'

export interface CorpusPassageRecord extends RetrievedPassage {
  sourceId: string
  domain: string
  sourceLanguage: string
  publicationDate: string | null
  isActive: boolean
  keywords: readonly string[]
  contentHash: string
  embedding: readonly number[]
  embeddingModel: string
  embeddingVersion: string
  embeddingDimensions: number
}

export type QueryEmbedder = (query: string, signal: AbortSignal) => Promise<number[] | null>

export interface QueryNormalization {
  originalQuery: string
  supplementalTerms: string[]
  preservedTokens: {
    amounts: string[]
    dates: string[]
    negations: string[]
    uncertainties: string[]
  }
  exactSectionRefs: string[]
}

export const LEGAL_CORPUS_COVERAGE_DECLARATION = {
  corpusVersion: LEGAL_CORPUS_BUNDLE.manifest.corpus_version,
  embeddingModel: LEGAL_CORPUS_BUNDLE.manifest.embedding_model,
  embeddingVersion: LEGAL_CORPUS_BUNDLE.manifest.embedding_version,
  embeddingDimensions: LEGAL_CORPUS_BUNDLE.manifest.embedding_dimensions,
  supportedDomains: [
    'Consumer refunds, defective goods, deficiency in service, and e-commerce grievances',
    'Financial fraud (BNS/BNSS post-1 July 2024 and historical IPC/CrPC pre-1 July 2024 transitional mapping)',
    'Banking & payment grievances (RBI unauthorised debit liability, PPI wallets, failed UPI/IMPS/ATM/card TAT & Rs 100/day compensation, card billing/closure, RB-IOS 2021)',
    'Free legal aid eligibility (NALSA / Legal Services Authorities Act, 1987 Section 12)',
  ],
  supportedRegions: ['India', 'Maharashtra', 'Bihar'],
  unsupportedCategories: [
    'Family/divorce/custody/maintenance disputes',
    'Income tax, GST, corporate, or securities (SEBI) adjudication',
    'Real estate RERA state-specific rules beyond SC Experion distinction',
    'Non-Indian jurisdictions',
    'State-specific consumer or police rules outside India-wide law, Maharashtra SCDRC, and Bihar regional reference',
  ],
} as const

// Thresholds are embedding-space specific. These values are qualified against the committed
// multilingual, historical, and unsupported-query fixtures and must move with corpus version.
const OPENAI_384_SPACE = LEGAL_CORPUS_BUNDLE.manifest.embedding_model === 'text-embedding-3-small'
const SEMANTIC_STRONG = OPENAI_384_SPACE ? 0.40 : 0.832
const SEMANTIC_CORROBORATED = OPENAI_384_SPACE ? 0.30 : 0.805

const STOPWORDS = new Set([
  'am', 'an', 'as', 'at', 'be', 'by', 'did', 'do', 'does', 'done', 'he', 'if', 'in', 'is', 'it',
  'its', 'me', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we', 'all', 'any', 'can', 'may',
  'now', 'out', 'own', 'per', 'she', 'too', 'use', 'way', 'why', 'yet',
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have', 'has', 'was', 'were', 'are', 'but',
  'not', 'what', 'when', 'where', 'which', 'who', 'how', 'could', 'would', 'should', 'will',
  'about', 'into', 'after', 'before', 'under', 'my', 'our', 'your', 'their', 'they', 'them', 'his',
  'her', 'him', 'you', 'india', 'indian', 'hai', 'hain', 'kya', 'kar', 'kare', 'karein',
  'karna', 'mera', 'meri', 'mere', 'mujhe', 'hum', 'aap', 'aur', 'par', 'mein', 'mai', 'ko', 'ka',
  'ki', 'ke', 'se', 'ne', 'ho', 'gaya', 'gayi', 'gaye', 'raha', 'rahi', 'rahe', 'hua', 'hui',
])

const TAX_OR_FILING_RETURN_RE = /\b(?:income\s+tax|tax|gst|itr)\s+return\b/i
const LEGAL_CONSUMER_INTENT_RE =
  /\b(?:consumer|complaint|grievance|commission|forum|court|refund|defect\w*|service|seller|marketplace|order|product|fraud|scam|bank|upi|card|police|fir|legal\s+aid)\b|उपभोक्ता|ग्राहक|शिकायत|रिफंड|धोखाधड़ी|बैंक|पुलिस/iu

const CROSS_LANG_CONCEPTS: ReadonlyArray<[RegExp, string]> = [
  [
    /\b(?:refund|paise\s+wapas|paisa\s+wapas|wapas\s+nahi|lotana|lauta|money\s+back|reimburse\w*)\b|रिफंड|वापसी|पैसे\s+वापस|पैसा\s+वापस/iu,
    'refund return price consideration seller e-commerce marketplace',
  ],
  [
    /\b(?:return\s+(?:policy|goods|product|item|order|money|price|amount)|refus\w*\s+to\s+return)\b/iu,
    'refund return price consideration seller e-commerce marketplace',
  ],
  [
    /\b(?:defect\w*|broken|damaged|faulty|kharab|kharaab|toota|tuta|bekar|nuksaan|spurious|fake\s+product)\b|खराब|टूटा|दोषपूर्ण|नकली/iu,
    'defect defective goods replacement repair product liability',
  ],
  [
    /\b(?:service|seva|late\s+delivery|delayed|non-delivery|deliver\s+nahi|pickup|grievance\s+officer|ticket\s+closed|customer\s+care)\b|सेवा|देरी|डिलीवरी|शिकायत\s+अधिकारी/iu,
    'deficiency service grievance officer 48 hours one month marketplace nch 1915',
  ],
  [
    /\b(?:consumer\s+(?:court|forum|commission)|district\s+commission|ejagriti|e-jagriti|upbhokta|grahak|nch|1915)\b|उपभोक्ता|ग्राहक\s+मंच|आयोग/iu,
    'consumer protection act district commission section 34 35 39 69 limitation jurisdiction pecuniary e-jagriti',
  ],
  [
    /\b(?:maharashtra|mumbai|thane|pune|nagpur|raigad|navi\s+mumbai|bandra)\b|महाराष्ट्र|मुंबई|पुणे|ठाणे/iu,
    'maharashtra state consumer disputes redressal commission district commission',
  ],
  [
    /\b(?:bihar|patna|nalanda|gaya|muzaffarpur|bhagalpur)\b|बिहार|पटना/iu,
    'bihar prohibition excise patna',
  ],
  [
    /\b(?:upi|imps|neft|rtgs|atm|debit\s+card|credit\s+card|wallet|paytm|phonepe|gpay|bhim|netbanking|net\s+banking)\b|यूपीआई|एटीएम|क्रेडिट\s+कार्ड|डेबिट\s+कार्ड|बैंक/iu,
    'rbi electronic banking transaction failed transaction tat compensation ppi wallet card',
  ],
  [
    /\b(?:debited|kat\s+gaye|kat\s+gaya|kata|deducted|failed\s+transaction|stuck|pending\s+reversal|not\s+credited|samne\s+wale\s+ko\s+nahi\s+mile|auto[- ]?revers\w*)\b|पैसे\s+कट\s+गए|खाते\s+से\s+कटे|असफल\s+लेनदेन/iu,
    'failed transaction auto-reversal t+1 t+5 100 per day compensation rbi tat circular',
  ],
  [
    /\b(?:unauthori[sz]ed|fraud\w*|scam\w*|phishing|dhokha|dhoka|dhokhadhadi|thagi|otp|pin|password|kyc|hacked|impersonat\w*|fake\s+call|customer\s+care\s+number|money\s+stolen|chori)\b|धोखाधड़ी|ठगी|अनधिकृत|फर्जी|ओटीपी|खाता\s+खाली/iu,
    'unauthorised electronic banking zero liability 3 working days customer negligence shared credentials cheating personation bns 318 319 ipc 420 cyber',
  ],
  [
    /\b(?:ombudsman|lokpal|30\s+days|bank\s+not\s+listening|bank\s+refused|unsolicited\s+card|card\s+close|closure|wrong\s+bill\w*|billing\s+dispute)\b|लोकपाल|बैंक\s+सुनवाई/iu,
    'integrated ombudsman scheme rb-ios 2021 cms.rbi.org.in 30 days card closure 7 working days billing dispute',
  ],
  [
    /\b(?:fir|police\s+station|thana|than[ae]|shikayat|zero\s+fir|magistrate|sp\b|dcp\b|police\s+refus\w*|fir\s+nahi)\b|थाना|पुलिस|एफआईआर|शिकायत/iu,
    'fir cognizable offence zero fir electronic fir bnss 173 175 crpc 154 magistrate',
  ],
  [
    /\b(?:free\s+lawyer|legal\s+aid|muft\s+vakil|vakil|nalsa|cannot\s+afford)\b|मुफ्त\s+वकील|विधिक\s+सहायता/iu,
    'legal services authorities act section 12 nalsa free legal aid',
  ],
]

const NEGATION_PATTERN =
  /\b(?:not|no|never|neither|nor|refused|refusing|denied|failed|without|nahi|nahee|nahin|mat|bina)\b|नहीं|मत|बिना/giu
const UNCERTAINTY_PATTERN =
  /\b(?:maybe|perhaps|unsure|uncertain|probably|might|possibly|shayad|pata\s+nahi|maloom\s+nahi)\b|शायद|पता\s+नहीं/giu
const AMOUNT_PATTERN = /(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?|\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:lakh|crore|rupees|rs)\b/gi
const DATE_PATTERN = /\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b/gi
const SECTION_REF_PATTERN = /\b(?:section|sec\.?|s\.|rule|r\.|para|article)\s*(\d+[a-z]?(?:\(\d+\))?(?:\([a-z]+\))?)\b/gi

// Signals clearly outside our bounded prototype domains (unless paired with supported consumer/banking/fraud intent).
const UNSUPPORTED_DOMAIN_PATTERN =
  /\b(?:divorce|alimony|child\s+custody|talaq|hindu\s+marriage\s+act|income\s+tax|gst\s+return|itr\s+filing|patent|trademark|copyright|immigration|visa|passport|landlord|tenant|evict\w*|rent\s+control|agricultural\s+land|encroach\w*|helmet|driving\s+licen[cs]e|challan|gratuity|provident\s+fund|epf\b|unpaid\s+salary|wrongful\s+termination|retrenchment|maternity\s+benefit|us\s+section\s+230|uk\s+consumer\s+rights|gdpr|hipaa|sebi\s+insider)\b/iu
const SUPPORTED_DOMAIN_OVERRIDE_PATTERN =
  /\b(?:consumer|e-?commerce|defective|refund|upi|imps|atm|credit\s+card|debit\s+card|wallet|bank|ombudsman|phishing|otp|unauthori[sz]ed|cheating|scam|nalsa|legal\s+aid)\b/iu

function isClearlyUnsupportedDomain(query: string): boolean {
  return UNSUPPORTED_DOMAIN_PATTERN.test(query) && !SUPPORTED_DOMAIN_OVERRIDE_PATTERN.test(query)
}

export function normalizeCrossLanguageQuery(query: string): QueryNormalization {
  const amounts = Array.from(new Set(query.match(AMOUNT_PATTERN) || []))
  const dates = Array.from(new Set(query.match(DATE_PATTERN) || []))
  const negations = Array.from(new Set((query.match(NEGATION_PATTERN) || []).map((s) => s.toLowerCase())))
  const uncertainties = Array.from(new Set((query.match(UNCERTAINTY_PATTERN) || []).map((s) => s.toLowerCase())))
  const exactSectionRefs: string[] = []
  for (const m of query.matchAll(SECTION_REF_PATTERN)) {
    exactSectionRefs.push(m[1].toLowerCase())
  }
  const hasTaxReturn = TAX_OR_FILING_RETURN_RE.test(query)
  const hasLegalConsumerIntent = LEGAL_CONSUMER_INTENT_RE.test(query)
  const supplementalTerms: string[] = []
  for (const [pattern, expansion] of CROSS_LANG_CONCEPTS) {
    if (hasTaxReturn && expansion.includes('e-commerce marketplace')) continue
    if (!hasLegalConsumerIntent && (expansion.includes('maharashtra state consumer') || expansion.includes('bihar prohibition'))) {
      continue
    }
    if (pattern.test(query)) {
      supplementalTerms.push(expansion)
    }
  }
  return {
    originalQuery: query,
    supplementalTerms,
    preservedTokens: { amounts, dates, negations, uncertainties },
    exactSectionRefs: Array.from(new Set(exactSectionRefs)),
  }
}

export function tokenizeText(text: string): string[] {
  const matches = text.toLowerCase().match(/[a-z0-9\u0900-\u097f]+(?:\([a-z0-9]+\))*/gu) || []
  return matches.filter((t) => t.length >= 2 && !STOPWORDS.has(t))
}

export function cosineSimilarity(a: readonly number[], b: readonly number[]): number {
  if (!a.length || a.length !== b.length) return 0
  let dot = 0
  let na = 0
  let nb = 0
  for (let i = 0; i < a.length; i++) {
    const x = a[i]
    const y = b[i]
    dot += x * y
    na += x * x
    nb += y * y
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb)
  return denom > 0 ? dot / denom : 0
}

function checkAbort(signal: AbortSignal): void {
  if (signal.aborted) {
    throw new DOMException('Retrieval aborted', 'AbortError')
  }
}

function isEffectiveForDate(
  passage: Pick<RetrievedPassage, 'validFrom' | 'validUntil' | 'dateIndependent'>,
  targetDate: string | null,
): boolean {
  if (passage.dateIndependent === true) return true
  if (!targetDate || !passage.validFrom) return false
  if (passage.validFrom > targetDate) return false
  if (passage.validUntil && targetDate >= passage.validUntil) return false
  return true
}

function toRetrievedPassage(p: CorpusPassageRecord, extraLimitations: string[] = []): RetrievedPassage {
  return {
    passageId: p.passageId,
    documentId: p.documentId,
    title: p.title,
    text: p.text,
    locator: p.locator,
    officialUrl: p.officialUrl,
    authority: p.authority,
    region: p.region,
    validFrom: p.validFrom,
    validUntil: p.validUntil,
    dateIndependent: p.dateIndependent,
    version: p.version,
    acquiredAt: p.acquiredAt,
    reviewState: p.reviewState,
    limitations: Array.from(new Set([...p.limitations, ...extraLimitations])),
    relatedPassageIds: [...p.relatedPassageIds],
  }
}

function formatDateOnly(val: unknown): string | null {
  if (val === null || val === undefined) return null
  if (val instanceof Date) return val.toISOString().slice(0, 10)
  const s = String(val).trim()
  return s ? s.slice(0, 10) : null
}

function collectTransitiveClosure(
  root: CorpusPassageRecord,
  byId: Map<string, CorpusPassageRecord>,
  alreadySelected: Set<string>,
): CorpusPassageRecord[] | null {
  const queue: CorpusPassageRecord[] = [root]
  const localSeen = new Set<string>()
  const additions: CorpusPassageRecord[] = []
  while (queue.length > 0) {
    const curr = queue.shift()!
    if (alreadySelected.has(curr.passageId) || localSeen.has(curr.passageId)) continue
    localSeen.add(curr.passageId)
    additions.push(curr)
    for (const relId of curr.relatedPassageIds) {
      if (alreadySelected.has(relId) || localSeen.has(relId)) continue
      const comp = byId.get(relId)
      if (!comp) return null
      queue.push(comp)
    }
  }
  return additions
}

/**
 * Ensures every returned passage satisfies retrieval-port.ts's transitive companion-passage
 * closure within request.limit.
 */
function selectWithCompanionClosure(
  ranked: CorpusPassageRecord[],
  byId: Map<string, CorpusPassageRecord>,
  limit: number,
  extraLimitations: Map<string, string[]>,
  outLimitations?: string[],
): RetrievedPassage[] {
  const selectedIds = new Set<string>()
  const ordered: CorpusPassageRecord[] = []
  let smallestSkippedClosure = Number.POSITIVE_INFINITY

  for (const candidate of ranked) {
    if (selectedIds.has(candidate.passageId)) continue
    const closure = collectTransitiveClosure(candidate, byId, selectedIds)
    if (!closure) continue
    if (ordered.length + closure.length > limit) {
      smallestSkippedClosure = Math.min(smallestSkippedClosure, closure.length)
      continue
    }
    for (const item of closure) {
      selectedIds.add(item.passageId)
      ordered.push(item)
    }
    if (ordered.length >= limit) break
  }

  if (ordered.length === 0 && Number.isFinite(smallestSkippedClosure) && outLimitations) {
    outLimitations.push(
      `Requested limit (${limit}) is smaller than the minimum required companion-passage closure (${smallestSkippedClosure}); increase limit to preserve definitions/exceptions.`,
    )
  }

  return ordered.map((p) => toRetrievedPassage(p, extraLimitations.get(p.passageId) || []))
}

export interface PackagedRetrieverOptions {
  passages?: readonly CorpusPassageRecord[]
  embedder?: QueryEmbedder | null
  minSemanticScore?: number
  corpusPendingWarnings?: readonly string[]
}

export function createHttpQueryEmbedder(config: {
  endpointUrl: string
  apiKey?: string
  model?: string
  timeoutMs?: number
}): QueryEmbedder {
  return async (query: string, signal: AbortSignal) => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), config.timeoutMs ?? 2500)
    const onAbort = () => controller.abort()
    signal.addEventListener('abort', onAbort, { once: true })
    try {
      const headers: Record<string, string> = { 'content-type': 'application/json' }
      if (config.apiKey) headers.authorization = `Bearer ${config.apiKey}`
      const res = await fetch(config.endpointUrl, {
        method: 'POST',
        headers,
        signal: controller.signal,
        body: JSON.stringify({
          input: `query: ${query}`,
          model: config.model ?? LEGAL_CORPUS_BUNDLE.manifest.embedding_model,
        }),
      })
      if (!res.ok) return null
      const json = (await res.json()) as {
        embedding?: number[]
        data?: Array<{ embedding?: number[] }>
      }
      const vec = json.embedding ?? json.data?.[0]?.embedding ?? null
      return Array.isArray(vec) && vec.length === LEGAL_CORPUS_BUNDLE.manifest.embedding_dimensions
        ? vec
        : null
    } catch {
      return null
    } finally {
      clearTimeout(timer)
      signal.removeEventListener('abort', onAbort)
    }
  }
}

export function createPackagedLegalRetriever(options: PackagedRetrieverOptions = {}): RetrieveEvidence {
  const allPassages = (options.passages ?? LEGAL_CORPUS_BUNDLE.passages) as readonly CorpusPassageRecord[]
  const minSemantic = options.minSemanticScore ?? SEMANTIC_STRONG

  // Precompute BM25 document frequencies once over the corpus
  const docTokens = new Map<string, string[]>()
  const docFreq = new Map<string, number>()
  let totalLen = 0
  for (const p of allPassages) {
    const toks = tokenizeText(`${p.title} ${p.locator} ${p.text} ${p.keywords.join(' ')}`)
    docTokens.set(p.passageId, toks)
    totalLen += toks.length
    for (const uniqueTok of new Set(toks)) {
      docFreq.set(uniqueTok, (docFreq.get(uniqueTok) || 0) + 1)
    }
  }
  const avgDocLen = allPassages.length ? totalLen / allPassages.length : 1

  return async (request: RetrievalRequest): Promise<RetrievalResult> => {
    checkAbort(request.signal)
    const query = (request.query || '').trim()
    const limit = Math.max(1, Math.min(request.limit || 6, 12))
    const limitations: string[] = []

    if (!query || query.length < 3) {
      return {
        passages: [],
        limitations: ['Query is empty or too short to establish legal support.'],
      }
    }

    if (isClearlyUnsupportedDomain(query)) {
      return {
        passages: [],
        limitations: [
          'Question appears outside the supported prototype scope (consumer refunds/defects/services, financial fraud, banking/payment grievances, and legal aid).',
        ],
      }
    }

    const norm = normalizeCrossLanguageQuery(query)
    const targetDate = request.incidentDate ?? request.asOfDate

    if (request.incidentDate === null) {
      limitations.push(
        `Incident date not confirmed; retrieved material reflects law in force on ${request.asOfDate} (pre-1 July 2024 IPC/CrPC or pre-20 July 2020 CPA 1986 may apply to older incidents). Current-law results must not be applied to an undated incident.`,
      )
    }
    if (request.region === null) {
      limitations.push(
        'Complaint region not confirmed; only national India-wide sources were searched (state-specific procedures such as Maharashtra SCDRC were excluded).',
      )
    } else if (!['India', 'Maharashtra', 'Bihar'].includes(request.region)) {
      limitations.push(
        `State-specific rules for ${request.region} are not yet in the verified prototype corpus; only national India-wide sources were searched.`,
      )
    }

    // Check pending review sources that relate to the query domain
    for (const p of allPassages) {
      if (p.reviewState === 'pending' && norm.supplementalTerms.some((t) => t.includes('e-commerce') || t.includes('ecommerce'))) {
        limitations.push(
          `Pending editorial verification: ${p.title} (${p.version}) is excluded from approved results until Gazette commencement is verified.`,
        )
        break
      }
    }

    // 1. Filter to applicable approved passages (strictly respecting region, date, reviewState, URL, size)
    const eligible = allPassages.filter((p) => {
      if (p.reviewState !== 'approved') return false
      if (!/^[\w.-]{1,100}$/.test(p.passageId) || p.passageId.startsWith('segment')) return false
      if (!p.text || p.text.length > 3200 || !p.officialUrl.startsWith('https://')) return false
      if (p.region !== 'India' && p.region !== request.region) return false
      if (!isEffectiveForDate(p, targetDate)) return false
      // Prefer active current versions when incidentDate is null, while permitting scheduled approved rules once validFrom arrives
      if (request.incidentDate === null && !p.isActive && !(p.validFrom && p.validFrom <= targetDate)) return false
      return true
    })

    if (!eligible.length) {
      return {
        passages: [],
        limitations: [
          ...limitations,
          `No approved passages matched region=${request.region ?? 'India'} and date=${targetDate}.`,
        ],
      }
    }

    const eligibleById = new Map(eligible.map((p) => [p.passageId, p]))

    // 2. Independent Lexical Branch (BM25 over original + normalized cross-language terms + exact section refs)
    const expandedQuery = [query, ...norm.supplementalTerms].join(' ')
    const qTokens = tokenizeText(expandedQuery)
    const k1 = 1.5
    const b = 0.75
    const N = allPassages.length || 1

    const lexicalScored: Array<{ id: string; score: number; exactSectionBoost: number; matchedCount: number }> = []
    for (const p of eligible) {
      const toks = docTokens.get(p.passageId) || []
      const dl = toks.length || 1
      const tfMap = new Map<string, number>()
      for (const t of toks) tfMap.set(t, (tfMap.get(t) || 0) + 1)

      let bm25 = 0
      let matchedCount = 0
      for (const qt of new Set(qTokens)) {
        const df = docFreq.get(qt) || 0
        if (!df) continue
        const tf = tfMap.get(qt) || 0
        if (!tf) continue
        matchedCount += 1
        const idf = Math.log(1 + (N - df + 0.5) / (df + 0.5))
        bm25 += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + (b * dl) / avgDocLen)))
      }

      let exactBoost = 0
      const locatorLower = `${p.title} ${p.locator}`.toLowerCase()
      for (const secRef of norm.exactSectionRefs) {
        if (locatorLower.includes(secRef) || p.text.toLowerCase().includes(`section ${secRef}`)) {
          exactBoost += 2.5
        }
      }
      // Also match specific statutory identifiers like 1930, 318, 420, 173, 154, 629
      for (const tok of query.toLowerCase().match(/\b(?:1930|1915|420|318|319|316|173|175|154|107|69|39|35|34|629|1417)\b/g) || []) {
        if (locatorLower.includes(tok) || p.passageId.includes(tok)) {
          exactBoost += 2.0
        }
      }

      const totalLex = bm25 + exactBoost
      if (totalLex > 0) {
        lexicalScored.push({ id: p.passageId, score: totalLex, exactSectionBoost: exactBoost, matchedCount })
      }
    }
    lexicalScored.sort((a, z) => z.score - a.score)

    // 3. Independent Semantic Embedding Branch (no keyword-match prerequisite!)
    let queryVec: number[] | null = null
    if (options.embedder) {
      checkAbort(request.signal)
      queryVec = await options.embedder(query, request.signal)
      checkAbort(request.signal)
      if (!queryVec) {
        limitations.push(
          'Semantic query embedder did not return a vector; retrieval fell back to lexical and cross-language query normalization only.',
        )
      }
    } else {
      limitations.push(
        'Semantic query embedder is not configured in this runtime; retrieval used lexical BM25 and cross-language query normalization only.',
      )
    }

    const semanticScored: Array<{ id: string; sim: number }> = []
    if (queryVec) {
      for (const p of eligible) {
        if (!p.embedding.length) continue
        const sim = cosineSimilarity(queryVec, p.embedding)
        semanticScored.push({ id: p.passageId, sim })
      }
      semanticScored.sort((a, z) => z.sim - a.sim)
    }

    // Check insufficient evidence / out-of-coverage guard
    const topSim = semanticScored[0]?.sim ?? 0
    const topLex = lexicalScored[0]?.score ?? 0
    const topMatchedCount = lexicalScored[0]?.matchedCount ?? 0
    const hasHighSemantic = topSim >= minSemantic
    const corroboratedFloor = options.minSemanticScore === undefined ? SEMANTIC_CORROBORATED : minSemantic - 0.032
    const hasCorroboratedHybrid = topSim >= corroboratedFloor && topLex >= 5.0 && topMatchedCount >= 2
    if (queryVec && !hasHighSemantic && !hasCorroboratedHybrid) {
      return {
        passages: [],
        limitations: [
          ...limitations,
          `Insufficient evidence in corpus: top semantic similarity (${topSim.toFixed(3)}) and lexical relevance (${topLex.toFixed(2)}) are below threshold; trigger bounded official-source research.`,
        ],
      }
    }
    if (!queryVec && (topLex < 4.5 || topMatchedCount < 2)) {
      return {
        passages: [],
        limitations: [
          ...limitations,
          'Insufficient lexical evidence in corpus for this query; trigger bounded official-source research.',
        ],
      }
    }

    // 4. Reciprocal Rank Fusion (RRF) + Regional/Historical Priority
    const rrfScores = new Map<string, number>()
    lexicalScored.slice(0, 24).forEach((item, idx) => {
      const rank = idx + 1
      rrfScores.set(item.id, (rrfScores.get(item.id) || 0) + 2 / (60 + rank) + Math.min(0.02, item.exactSectionBoost * 0.005))
    })
    semanticScored.slice(0, 24).forEach((item, idx) => {
      const fusionFloor = options.minSemanticScore === undefined ? SEMANTIC_CORROBORATED : minSemantic - 0.035
      if (item.sim < fusionFloor) return
      const rank = idx + 1
      rrfScores.set(item.id, (rrfScores.get(item.id) || 0) + 1 / (60 + rank))
    })

    // If user confirmed a specific state (e.g. Maharashtra), boost applicable regional guidance slightly when relevant
    if (request.region && request.region !== 'India') {
      for (const [id, score] of rrfScores.entries()) {
        const p = eligibleById.get(id)
        if (p && p.region === request.region) {
          rrfScores.set(id, score + 0.004)
        }
      }
    }

    const ranked = Array.from(rrfScores.entries())
      .sort((a, z) => z[1] - a[1])
      .map(([id]) => eligibleById.get(id)!)
      .filter(Boolean)

    if (!ranked.length) {
      return {
        passages: [],
        limitations: [
          ...limitations,
          'No eligible passages passed combined semantic/lexical relevance filtering.',
        ],
      }
    }

    const extraNotes = new Map<string, string[]>()
    for (const p of ranked) {
      if (p.validUntil && request.incidentDate) {
        extraNotes.set(p.passageId, [
          `Historical version valid ${p.validFrom ?? 'unknown'} to ${p.validUntil} for incidentDate=${request.incidentDate}.`,
        ])
      }
    }

    const selected = selectWithCompanionClosure(ranked, eligibleById, limit, extraNotes, limitations)
    return {
      passages: selected,
      limitations: Array.from(new Set(limitations)),
    }
  }
}

export interface SupabaseHybridRpcRow {
  passage_id: string
  document_id: string
  title: string
  text: string
  locator: string
  official_url: string
  authority: string
  region: string
  valid_from: string | Date | null
  valid_until: string | Date | null
  date_independent: boolean
  version: string
  acquired_at: string | Date
  review_state: 'approved' | 'pending' | 'retired'
  limitations: string[]
  related_passage_ids: string[]
  lexical_rank: number | null
  semantic_rank: number | null
  cosine_score: number
  rrf_score: number
}

export function createSupabaseLegalRetriever(deps: {
  rpc: (
    name: string,
    args: Record<string, unknown>,
    signal: AbortSignal,
  ) => Promise<SupabaseHybridRpcRow[]>
  fetchPassagesByIds: (ids: string[], signal: AbortSignal) => Promise<SupabaseHybridRpcRow[]>
  embedder?: QueryEmbedder | null
}): RetrieveEvidence {
  return async (request: RetrievalRequest): Promise<RetrievalResult> => {
    checkAbort(request.signal)
    const query = (request.query || '').trim()
    const limit = Math.max(1, Math.min(request.limit || 6, 12))
    const limitations: string[] = []

    if (!query || query.length < 3) {
      return { passages: [], limitations: ['Query is empty or too short.'] }
    }
    if (isClearlyUnsupportedDomain(query)) {
      return {
        passages: [],
        limitations: [
          'Question appears outside the supported prototype scope (consumer refunds/defects/services, financial fraud, banking/payment grievances, and legal aid).',
        ],
      }
    }

    const targetDate = request.incidentDate ?? request.asOfDate
    if (request.incidentDate === null) {
      limitations.push(
        `General information as of ${request.asOfDate}. Historical incidents may be governed by different rules.`,
      )
    }
    if (request.region === null) {
      limitations.push('Complaint region not confirmed; searched national India-wide sources only.')
    } else if (!['India', 'Maharashtra', 'Bihar'].includes(request.region)) {
      limitations.push(
        `State-specific rules for ${request.region} are not yet in the verified prototype corpus; only national India-wide sources were searched.`,
      )
    }

    const norm = normalizeCrossLanguageQuery(query)
    const expandedQuery = [query, ...norm.supplementalTerms].join(' ')
    const cleanedSqlQuery = tokenizeText(expandedQuery).join(' ') || query

    let queryEmbedding: number[] | null = null
    if (deps.embedder) {
      queryEmbedding = await deps.embedder(query, request.signal)
      checkAbort(request.signal)
      if (!queryEmbedding) {
        limitations.push('Semantic query embedder unavailable; SQL search used tsvector lexical branch only.')
      }
    } else {
      limitations.push('Semantic query embedder not configured; SQL search used tsvector lexical branch only.')
    }

    const rows = await deps.rpc(
      'nyay_legal_hybrid_search',
      {
        p_query: cleanedSqlQuery,
        p_query_embedding: queryEmbedding,
        p_region: request.region,
        p_incident_date: request.incidentDate,
        p_as_of_date: request.asOfDate,
        p_limit: Math.min(limit * 2, 16),
      },
      request.signal,
    )
    checkAbort(request.signal)

    if (!rows.length) {
      return {
        passages: [],
        limitations: [...limitations, 'No applicable passages found in PostgreSQL legal corpus.'],
      }
    }

    // Check insufficient evidence / out-of-coverage guard identically to packaged retriever
    const qTokSet = new Set(tokenizeText(expandedQuery))
    let maxTokenHits = 0
    let maxCosine = 0
    for (const r of rows) {
      maxCosine = Math.max(maxCosine, Number(r.cosine_score || 0))
      const rowToks = new Set(tokenizeText(`${r.title} ${r.locator} ${r.text}`))
      let hits = 0
      for (const qt of qTokSet) {
        if (rowToks.has(qt)) hits++
      }
      maxTokenHits = Math.max(maxTokenHits, hits)
    }
    if (queryEmbedding && maxCosine < SEMANTIC_STRONG && !(maxCosine >= SEMANTIC_CORROBORATED && maxTokenHits >= 2)) {
      return {
        passages: [],
        limitations: [
          ...limitations,
          `Insufficient evidence in PostgreSQL legal corpus: top cosine similarity (${maxCosine.toFixed(3)}) and domain token overlap (${maxTokenHits}) are below threshold; trigger bounded official-source research.`,
        ],
      }
    }
    if (!queryEmbedding && maxTokenHits < 2) {
      return {
        passages: [],
        limitations: [
          ...limitations,
          'Insufficient lexical evidence in PostgreSQL legal corpus for this query; trigger bounded official-source research.',
        ],
      }
    }

    // Fetch transitive companion passages referenced in related_passage_ids
    const byId = new Map<string, SupabaseHybridRpcRow>(rows.map((r) => [r.passage_id, r]))
    for (let hop = 0; hop < 3; hop++) {
      const missingCompIds = new Set<string>()
      for (const r of byId.values()) {
        for (const compId of r.related_passage_ids || []) {
          if (!byId.has(compId)) missingCompIds.add(compId)
        }
      }
      if (!missingCompIds.size) break
      const comps = await deps.fetchPassagesByIds(Array.from(missingCompIds), request.signal)
      checkAbort(request.signal)
      if (!comps.length) break
      for (const c of comps) byId.set(c.passage_id, c)
    }

    const toRecord = (r: SupabaseHybridRpcRow): RetrievedPassage => ({
      passageId: r.passage_id,
      documentId: r.document_id,
      title: r.title,
      text: r.text,
      locator: r.locator,
      officialUrl: r.official_url,
      authority: r.authority,
      region: r.region,
      validFrom: formatDateOnly(r.valid_from),
      validUntil: formatDateOnly(r.valid_until),
      dateIndependent: r.date_independent,
      version: r.version,
      acquiredAt: r.acquired_at instanceof Date ? r.acquired_at.toISOString() : String(r.acquired_at),
      reviewState: r.review_state,
      limitations: r.limitations || [],
      relatedPassageIds: r.related_passage_ids || [],
    })

    const asCorpusMap = new Map<string, CorpusPassageRecord>()
    for (const r of byId.values()) {
      if (r.review_state !== 'approved') continue
      const rec = toRecord(r)
      if (rec.region !== 'India' && rec.region !== request.region) continue
      if (!isEffectiveForDate(rec, targetDate)) continue
      asCorpusMap.set(r.passage_id, {
        ...rec,
        sourceId: r.document_id,
        domain: 'consumer',
        sourceLanguage: 'en',
        publicationDate: null,
        isActive: true,
        keywords: [],
        contentHash: '',
        embedding: [],
        embeddingModel: LEGAL_CORPUS_BUNDLE.manifest.embedding_model,
        embeddingVersion: LEGAL_CORPUS_BUNDLE.manifest.embedding_version,
        embeddingDimensions: LEGAL_CORPUS_BUNDLE.manifest.embedding_dimensions,
      })
    }
    const rankedCorpus = rows.map((r) => asCorpusMap.get(r.passage_id)).filter(Boolean) as CorpusPassageRecord[]
    const selected = selectWithCompanionClosure(rankedCorpus, asCorpusMap, limit, new Map(), limitations)

    return {
      passages: selected,
      limitations: Array.from(new Set(limitations)),
    }
  }
}
