-- Read-only operator queries; run with an authorized backend/database role.
-- Contains metrics and opaque execution IDs, not prompts, emails or document text.

-- Recent runs: reserved/accounted money includes holds, not necessarily incurred charges.
select r.execution_id,t.status,r.runtime,r.pricing_version,
  r.reserved_usd,r.accounted_usd,r.terminal,r.created_at,r.finished_at,
  t.error_detail->>'code' as error_code
from public.nyay_runtime_runs r join public.nyay_turn_executions t on t.id=r.execution_id
order by r.created_at desc limit 50;

-- Active worker time, excluding queued/model waiting between executions. This is not CPU time.
select stage,count(*) as executions,
  count(*) filter(where outcome='retry') as repeated_steps,
  count(*) filter(where outcome='waiting') as pending_polls,
  count(*) filter(where outcome='fenced') as fenced_steps,
  count(*) filter(where outcome='failed') as failed_steps,
  round(avg(duration_ms),2) as mean_active_ms,
  percentile_cont(0.95) within group(order by duration_ms) as p95_active_ms
from public.nyay_runtime_steps where created_at>=now()-interval '24 hours'
group by stage order by stage;

-- Recorded provider usage is distinct from uncertain accepted calls.
select r.runtime->>'model' as model,count(*) as calls,
  count(*) filter(where c.actual_usd is null) as calls_without_usage,
  sum(c.input_tokens) as input_tokens,sum(c.cached_tokens) as cached_input_tokens,
  sum(c.cache_write_tokens) as cache_write_tokens,
  sum(c.output_tokens) as output_tokens,sum(c.reasoning_tokens) as reasoning_tokens,
  sum(c.actual_usd) as observed_usage_estimate_usd
from public.nyay_runtime_calls c join public.nyay_runtime_runs r on r.execution_id=c.execution_id
where c.created_at>=now()-interval '24 hours' group by r.runtime->>'model';
