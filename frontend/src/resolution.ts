export interface RouteOption {
  route_id:string;recipient_id:string;title:string;channel:string;reason:string;
  eligibility:{status:string;reasons:string[];missing_inputs:string[]};preparation:string[];instructions:string[];source_urls:string[];
  tradeoff:{filing_fee_inr:string|null;fee_basis:string;effort:string;effort_basis:string;waiting_time:string;other_costs:string[];uncertainty:string[]}
}
export interface Journey {
  events:{id:string;event_type:string;description:string;occurred_at:string|null;recorded_at:string;evidence_status:string;recipient:string|null;reference:string|null;supersedes_id:string|null}[];
  submissions:{id:string;recipient:string;reference:string|null;submitted_at:string|null;channel:string}[];
  commitments:{event_id:string;description:string;due_at:string|null;status:string}[];
  outcome:string;satisfaction:string;severity:string;
  recommendations:{id:string;recommended_route_id:string|null;case_version:number;stale:boolean;alternatives:RouteOption[];important_uncertainties:string[];status:string}[]
}
