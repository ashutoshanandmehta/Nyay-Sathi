import type { RetrievedPassage } from '../../../supabase/functions/nyay-api/retrieval-port'

// Synthetic fixtures. Example domains and passages must never be used in production.
export const refundEvidence: RetrievedPassage = {
  passageId:'fixture-refund-v2',documentId:'fixture-consumer-act',title:'Synthetic consumer rule',
  text:'A consumer may ask for a refund for a defective product when the defect is documented.',
  locator:'Fixture § 1',officialUrl:'https://legal.example.invalid/fixture',authority:'Synthetic authority',
  region:'India',validFrom:'2020-01-01',validUntil:null,version:'v2',
  acquiredAt:'2026-11-20T00:00:00Z',reviewState:'approved',limitations:['Fixture only'],relatedPassageIds:[],
}
export const bankingEvidence: RetrievedPassage = {
  ...refundEvidence,passageId:'fixture-banking-v1',documentId:'fixture-banking-rule',version:'v1',
  text:'A customer may ask the bank for a reference number for a disputed transfer.',
}
export const retiredEvidence: RetrievedPassage = {
  ...refundEvidence,passageId:'fixture-refund-v1',version:'v1',reviewState:'retired',validUntil:'2020-01-01',
}
export const regionalEvidence: RetrievedPassage = {
  ...refundEvidence,passageId:'fixture-region-v1',region:'Karnataka',relatedPassageIds:[refundEvidence.passageId],
}
