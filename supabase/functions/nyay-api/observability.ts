// Content-free operational events. Never accept arbitrary provider errors or user metadata.
export interface StepObservation {
  stage:string;attempt:number;durationMs:number;outcome:'advanced'|'fenced'|'waiting'|'retry'|'failed'
  evidenceCount?:number;acceptedClaims?:number;blockedClaims?:number
}
export function operationalLog(executionId:string,event:StepObservation):void {
  const stage=/^[a-z_]{1,40}$/.test(event.stage)?event.stage:'unknown'
  console.info(JSON.stringify({type:'nyay.agent.step',execution_id:executionId,stage,
    attempt:event.attempt,duration_ms:Math.max(0,Math.round(event.durationMs)),outcome:event.outcome,
    ...(event.evidenceCount===undefined?{}:{evidence_count:event.evidenceCount}),
    ...(event.acceptedClaims===undefined?{}:{accepted_claims:event.acceptedClaims}),
    ...(event.blockedClaims===undefined?{}:{blocked_claims:event.blockedClaims}),
  }))
}
