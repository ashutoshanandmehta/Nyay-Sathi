// Shared with Antigravity. Dates and region must come from confirmed case data.
export interface RetrievalRequest {
  query: string
  region: string | null
  incidentDate: string | null
  asOfDate: string
  dateBasis?: RetrievalDateBasis
  limit: number
  signal: AbortSignal
}
export interface RetrievedPassage {
  passageId: string
  documentId: string
  title: string
  text: string
  locator: string
  officialUrl: string
  authority: string
  region: string
  validFrom: string | null
  validUntil: string | null
  dateIndependent?: boolean
  version: string
  acquiredAt: string
  reviewState: 'approved' | 'pending' | 'retired'
  limitations: string[]
  relatedPassageIds: string[]
}
export interface RetrievalResult {
  passages: RetrievedPassage[]
  limitations: string[]
}
export type RetrieveEvidence = (request: RetrievalRequest)=>Promise<RetrievalResult>
export type RetrievalDateBasis = 'confirmed_incident' | 'general_current_law' | 'incident_date_required'

export function retrievalDateBasis(message: string, incidentDate: string | null): RetrievalDateBasis {
  if (incidentDate) return 'confirmed_incident'
  const query = message.normalize('NFKC').toLowerCase()
  // Default to requiring a confirmed date. A first-person or historical query is not
  // promoted to current law simply because it contains a question about rules.
  const caseSpecific = /\b(my|mine|i|me|we|our|yesterday|last|ago|before|previous|happened|mera|meri|mere|maine|mujhe|humara|hamara|kal|pichle|hua|hui|gaye|gaya)\b|(?:मेरा|मेरी|मेरे|मैंने|मुझे|हमारा|हमारे|पिछले|कल|हुआ|हुई)|\b(?:19|20)\d{2}\b/u
  const general = /\b(?:what (?:are|is) (?:the |current )?(?:rules?|law|procedure|legal|rights?|time limit)|generally|current (?:law|rules?)|kya (?:niyam|kanoon)|aaj ke niyam)\b|(?:क्या नियम|क्या कानून|सामान्यतः|वर्तमान नियम|मौजूदा कानून)/u
  return !caseSpecific.test(query) && general.test(query) ? 'general_current_law' : 'incident_date_required'
}

export function applicablePassages(results: RetrievalResult, request: RetrievalRequest): RetrievedPassage[] {
  const candidates = results.passages.slice(0,request.limit).filter(p => {
    let url: URL
    try { url = new URL(p.officialUrl) } catch { return false }
    const date = request.incidentDate ?? (request.dateBasis === 'general_current_law' ? request.asOfDate : null)
    return p.reviewState==='approved' && /^[\w.-]{1,100}$/.test(p.passageId)
      && !p.passageId.startsWith('segment') && Boolean(p.version && p.documentId && p.locator && p.text)
      && p.text.length<=3200 && url.protocol==='https:' && !url.username && !url.password
      && (p.region==='India' || p.region===request.region)
      && (p.dateIndependent===true || (date!==null && p.validFrom!==null && p.validFrom<=date && (!p.validUntil || date<p.validUntil)))
  })
  let eligible=candidates.filter(p=>candidates.filter(q=>q.passageId===p.passageId).length===1)
  while(true) {
    const ids=new Set(eligible.map(p=>p.passageId))
    const next=eligible.filter(p=>p.relatedPassageIds.every(id=>ids.has(id)))
    if(next.length===eligible.length) return next
    eligible=next
  }
}
