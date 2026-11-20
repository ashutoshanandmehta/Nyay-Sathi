-- Content-free, service-only accounting and traces for the resumable agent.
alter table public.nyay_usage_budgets alter column estimated_spend_usd type numeric(18,9);
create table public.nyay_runtime_runs (
  execution_id uuid primary key,
  owner_id uuid not null,
  budget_date date not null default current_date,
  runtime jsonb not null,
  input_rate numeric not null,
  cached_rate numeric not null,
  output_rate numeric not null,
  pricing_version text not null default '2026-11-20-standard-30m',
  reserved_usd numeric not null check (reserved_usd>=0),
  call_reserve_usd numeric not null check (call_reserve_usd>0),
  accounted_usd numeric not null check (accounted_usd>=0),
  terminal boolean not null default false,
  created_at timestamptz not null default clock_timestamp(),
  finished_at timestamptz,
  foreign key(execution_id,owner_id) references public.nyay_turn_executions(id,owner_id) on delete cascade
);
create index nyay_runtime_runs_owner on public.nyay_runtime_runs(owner_id,created_at desc);
create table public.nyay_runtime_calls (
  intent uuid primary key,
  execution_id uuid not null references public.nyay_runtime_runs on delete cascade,
  stage text not null check(stage in ('primary','review','repair')),
  response_id text unique,
  status text not null default 'unconfirmed',
  input_tokens bigint,
  cached_tokens bigint,
  cache_write_tokens bigint,
  cache_write_30m_tokens bigint,
  cache_write_12h_tokens bigint,
  output_tokens bigint,
  reasoning_tokens bigint,
  actual_usd numeric,
  created_at timestamptz not null default clock_timestamp(),
  observed_at timestamptz
);
create index nyay_runtime_calls_run on public.nyay_runtime_calls(execution_id,created_at);
create table public.nyay_runtime_steps (
  id bigint generated always as identity primary key,
  execution_id uuid not null references public.nyay_runtime_runs on delete cascade,
  lease_token uuid not null,
  stage text not null,
  attempt integer not null,
  duration_ms integer not null,
  outcome text not null,
  evidence_count integer not null default 0,
  blocked_claims integer not null default 0,
  created_at timestamptz not null default clock_timestamp(),
  unique(execution_id,lease_token,stage)
);
create index nyay_runtime_steps_run on public.nyay_runtime_steps(execution_id,created_at);
alter table public.nyay_runtime_runs enable row level security;
alter table public.nyay_runtime_calls enable row level security;
alter table public.nyay_runtime_steps enable row level security;
revoke all on public.nyay_runtime_runs,public.nyay_runtime_calls,public.nyay_runtime_steps from public,anon,authenticated;
grant select,insert,update,delete on public.nyay_runtime_runs,public.nyay_runtime_calls,public.nyay_runtime_steps to service_role;
grant usage,select on sequence public.nyay_runtime_steps_id_seq to service_role;

-- Keep the original atomic publication/admission logic; wrap it with accounting.
alter function public.nyay_resume_admit(uuid,uuid,text,jsonb,numeric) rename to nyay_resume_admit_core;
create function public.nyay_resume_admit(p_owner uuid,p_chat uuid,p_request text,p_payload jsonb,p_reserve numeric,p_runtime jsonb)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare result jsonb; per_call numeric; in_rate numeric; out_rate numeric; config jsonb;
begin
  if coalesce(p_runtime->>'model','') not in ('gpt-6.2-sol','gpt-6.2-astra')
    or coalesce(p_runtime->>'reasoning','') not in ('low','medium','high')
    or coalesce(p_runtime->>'maxOutputTokens','') !~ '^[0-9]{4}$'
    or (p_runtime->>'maxOutputTokens')::integer not between 1024 and 8192 then
    return '{"error":"configuration"}';
  end if;
  in_rate=case when p_runtime->>'model'='gpt-6.2-sol' then 2 else 8 end;
  out_rate=case when p_runtime->>'model'='gpt-6.2-sol' then 10 else 40 end;
  per_call=ceil((72192*in_rate*1.25+(p_runtime->>'maxOutputTokens')::integer*out_rate)*1000)/1000000000;
  if p_reserve is distinct from per_call*6 then return '{"error":"configuration"}'; end if;
  config=jsonb_build_object('model',p_runtime->>'model','reasoning',p_runtime->>'reasoning',
    'maxOutputTokens',(p_runtime->>'maxOutputTokens')::integer);
  result=public.nyay_resume_admit_core(p_owner,p_chat,p_request,p_payload,p_reserve);
  if result ? 'error' then return result; end if;
  insert into public.nyay_runtime_runs(execution_id,owner_id,runtime,input_rate,cached_rate,output_rate,reserved_usd,call_reserve_usd,accounted_usd)
  values((result->>'execution_id')::uuid,p_owner,config,in_rate,in_rate/20,out_rate,p_reserve,per_call,p_reserve) on conflict do nothing;
  update public.nyay_turn_work w set checkpoint=jsonb_set(w.checkpoint,'{runtime}',r.runtime)
  from public.nyay_runtime_runs r where w.execution_id=(result->>'execution_id')::uuid
    and r.execution_id=w.execution_id and not w.checkpoint ? 'runtime';
  return result;
end $$;

-- Admission and settlement serialize on the same project budget lock. Unknown
-- accepted submissions keep a per-call reserve; missing usage is never treated as zero.
create function public.nyay_settle_run(p_id uuid,p_terminal boolean default false)
returns void language plpgsql security invoker set search_path='' as $$
declare r public.nyay_runtime_runs; charge numeric;
begin
  perform pg_advisory_xact_lock(81923514);
  select * into r from public.nyay_runtime_runs where execution_id=p_id for update;
  if not found then return; end if;
  if r.terminal or p_terminal then
    select coalesce(sum(coalesce(actual_usd,r.call_reserve_usd)),0) into charge
    from public.nyay_runtime_calls where execution_id=p_id;
  else
    select greatest(r.reserved_usd,coalesce(sum(actual_usd),0)) into charge
    from public.nyay_runtime_calls where execution_id=p_id;
  end if;
  update public.nyay_usage_budgets set estimated_spend_usd=greatest(0,estimated_spend_usd+charge-r.accounted_usd),
    updated_at=clock_timestamp() where owner_id=r.owner_id and window_date=r.budget_date;
  update public.nyay_runtime_runs set accounted_usd=charge,terminal=terminal or p_terminal,
    finished_at=case when terminal or p_terminal then coalesce(finished_at,clock_timestamp()) end where execution_id=p_id;
end $$;

alter function public.nyay_resume_advance(uuid,uuid,text,jsonb,integer,jsonb,boolean) rename to nyay_resume_advance_core;
create function public.nyay_resume_advance(p_id uuid,p_token uuid,p_stage text,p_state jsonb,p_delay integer,p_event jsonb default null,p_keep_lease boolean default false)
returns boolean language plpgsql security invoker set search_path='' as $$
declare changed boolean;
begin
  changed=public.nyay_resume_advance_core(p_id,p_token,p_stage,p_state,p_delay,p_event,p_keep_lease);
  if not changed then return false; end if;
  if p_stage='submitting' and exists(select 1 from public.nyay_runtime_runs where execution_id=p_id) then
    if not exists(select 1 from public.nyay_runtime_calls where intent=(p_state->>'intent')::uuid)
      and (select count(*) from public.nyay_runtime_calls where execution_id=p_id)>=6 then
      raise exception 'Submission budget exhausted';
    end if;
    insert into public.nyay_runtime_calls(intent,execution_id,stage)
    values((p_state->>'intent')::uuid,p_id,p_state->'model'->>'stage') on conflict do nothing;
  elsif p_stage='collect' then
    update public.nyay_runtime_calls set response_id=p_state->>'responseId',status='submitted'
      where intent=(p_state->>'intent')::uuid and execution_id=p_id and actual_usd is null;
  end if;
  if p_stage in ('publish','failed','discard') then perform public.nyay_settle_run(p_id,true); end if;
  return true;
end $$;

alter function public.nyay_resume_cancel(uuid,uuid,text) rename to nyay_resume_cancel_core;
create function public.nyay_resume_cancel(p_owner uuid,p_chat uuid,p_request text)
returns boolean language plpgsql security invoker set search_path='' as $$
declare changed boolean; run_id uuid;
begin
  changed=public.nyay_resume_cancel_core(p_owner,p_chat,p_request);
  if changed then
    select id into run_id from public.nyay_turn_executions where owner_id=p_owner and conversation_id=p_chat and request_id=p_request;
    perform public.nyay_settle_run(run_id,true);
  end if;
  return changed;
end $$;

create function public.nyay_record_model_response(p_id uuid,p_intent uuid,p_response text,p_status text,p_usage jsonb)
returns void language plpgsql security invoker set search_path='' as $$
declare c public.nyay_runtime_calls; r public.nyay_runtime_runs;
  incoming bigint; outgoing bigint; cached bigint; reasoning bigint; writes bigint; short_writes bigint; long_writes bigint; cost numeric;
begin
  if p_status not in ('completed','failed','incomplete','cancelled') or p_response !~ '^resp_[A-Za-z0-9_-]{1,150}$' then
    raise exception 'Invalid provider result';
  end if;
  -- Fixed lock order for admission, late webhook reconciliation, cancellation and settlement.
  perform pg_advisory_xact_lock(81923514);
  select * into c from public.nyay_runtime_calls where intent=p_intent;
  if not found then return; end if;
  if (p_id is not null and c.execution_id<>p_id) or (c.response_id is not null and c.response_id<>p_response) then
    raise exception 'Provider receipt mismatch';
  end if;
  select * into r from public.nyay_runtime_runs where execution_id=c.execution_id for update;
  if p_usage is not null then
    if coalesce(p_usage->>'input_tokens','') !~ '^[0-9]{1,10}$'
      or coalesce(p_usage->>'output_tokens','') !~ '^[0-9]{1,10}$'
      or coalesce(p_usage->'input_tokens_details'->>'cached_tokens','0') !~ '^[0-9]{1,10}$'
      or coalesce(p_usage->'input_tokens_details'->>'cache_write_tokens','0') !~ '^[0-9]{1,10}$'
      or coalesce(p_usage->'input_tokens_details'->'cache_write_tokens_details'->>'ttl_30m_tokens','0') !~ '^[0-9]{1,10}$'
      or coalesce(p_usage->'input_tokens_details'->'cache_write_tokens_details'->>'ttl_12h_tokens','0') !~ '^[0-9]{1,10}$'
      or coalesce(p_usage->'output_tokens_details'->>'reasoning_tokens','0') !~ '^[0-9]{1,10}$' then
      raise exception 'Invalid provider usage';
    end if;
    incoming=(p_usage->>'input_tokens')::bigint; outgoing=(p_usage->>'output_tokens')::bigint;
    cached=coalesce(p_usage->'input_tokens_details'->>'cached_tokens','0')::bigint;
    writes=coalesce(p_usage->'input_tokens_details'->>'cache_write_tokens','0')::bigint;
    long_writes=coalesce(p_usage->'input_tokens_details'->'cache_write_tokens_details'->>'ttl_12h_tokens','0')::bigint;
    short_writes=coalesce((p_usage->'input_tokens_details'->'cache_write_tokens_details'->>'ttl_30m_tokens')::bigint,writes-long_writes);
    reasoning=coalesce(p_usage->'output_tokens_details'->>'reasoning_tokens','0')::bigint;
    if cached+writes>incoming or short_writes<0 or short_writes+long_writes<>writes or reasoning>outgoing then raise exception 'Invalid token breakdown'; end if;
    cost=ceil(((incoming-cached-writes)*r.input_rate+cached*r.cached_rate+
      short_writes*r.input_rate*1.25+long_writes*r.input_rate*2.5+outgoing*r.output_rate+
      case when p_usage->'input_tokens_details'->>'cache_write_tokens' is null then (incoming-cached)*r.input_rate*0.25 else 0 end)*1000)/1000000000;
    if c.actual_usd is not null and (c.input_tokens<>incoming or c.output_tokens<>outgoing
      or c.cached_tokens<>cached or c.reasoning_tokens<>reasoning or c.cache_write_tokens<>writes
      or c.cache_write_30m_tokens<>short_writes or c.cache_write_12h_tokens<>long_writes) then raise exception 'Provider usage changed'; end if;
    update public.nyay_runtime_calls set response_id=p_response,status=p_status,input_tokens=incoming,
      output_tokens=outgoing,cached_tokens=cached,
      cache_write_tokens=case when p_usage->'input_tokens_details'->>'cache_write_tokens' is not null then writes end,
      cache_write_30m_tokens=case when p_usage->'input_tokens_details'->>'cache_write_tokens' is not null then short_writes end,
      cache_write_12h_tokens=case when p_usage->'input_tokens_details'->>'cache_write_tokens' is not null then long_writes end,
      reasoning_tokens=reasoning,actual_usd=cost,observed_at=coalesce(observed_at,clock_timestamp())
      where intent=p_intent;
  else
    update public.nyay_runtime_calls set response_id=p_response,status=p_status,observed_at=coalesce(observed_at,clock_timestamp())
      where intent=p_intent;
  end if;
  perform public.nyay_settle_run(c.execution_id,false);
end $$;

create function public.nyay_record_step(p_id uuid,p_lease uuid,p_stage text,p_attempt integer,p_duration integer,p_outcome text,p_evidence integer,p_blocked integer)
returns void language plpgsql security invoker set search_path='' as $$
begin
  if p_stage !~ '^[a-z_]{1,40}$' or p_outcome not in ('advanced','fenced','waiting','retry','failed')
    or p_attempt<0 or p_duration<0 or p_duration>150000 or p_evidence<0 or p_blocked<0 then
    raise exception 'Invalid step observation';
  end if;
  insert into public.nyay_runtime_steps(execution_id,lease_token,stage,attempt,duration_ms,outcome,evidence_count,blocked_claims)
  select p_id,p_lease,p_stage,p_attempt,p_duration,p_outcome,p_evidence,p_blocked
  where exists(select 1 from public.nyay_runtime_runs where execution_id=p_id)
  on conflict(execution_id,lease_token,stage) do nothing;
end $$;

create function public.nyay_run_observability(p_owner uuid,p_chat uuid,p_request text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare run_id uuid; result jsonb;
begin
  select id into run_id from public.nyay_turn_executions where owner_id=p_owner and conversation_id=p_chat and request_id=p_request;
  if not found then return null; end if;
  select jsonb_build_object('status',t.status,'runtime',r.runtime,'reserved_usd',r.reserved_usd,
    'accounted_usd',r.accounted_usd,'terminal',r.terminal,'budget_date',r.budget_date,'pricing_version',r.pricing_version,
    'elapsed_ms',round(extract(epoch from(coalesce(r.finished_at,clock_timestamp())-r.created_at))*1000),
    'error_code',t.error_detail->>'code',
    'calls',coalesce((select jsonb_agg(jsonb_build_object('stage',c.stage,'status',c.status,
      'input_tokens',c.input_tokens,'cached_tokens',c.cached_tokens,'output_tokens',c.output_tokens,
      'cache_write_tokens',c.cache_write_tokens,'cache_write_30m_tokens',c.cache_write_30m_tokens,'cache_write_12h_tokens',c.cache_write_12h_tokens,
      'cache_write_breakdown_known',c.cache_write_tokens is not null,
      'reasoning_tokens',c.reasoning_tokens,'estimated_actual_usd',c.actual_usd,
      'observed_duration_ms',case when c.observed_at is not null then round(extract(epoch from(c.observed_at-c.created_at))*1000) end,
      'usage_confirmed',c.actual_usd is not null) order by c.created_at)
      from public.nyay_runtime_calls c where c.execution_id=run_id),'[]'::jsonb),
    'steps',coalesce((select jsonb_agg(jsonb_build_object('stage',s.stage,'attempt',s.attempt,
      'duration_ms',s.duration_ms,'outcome',s.outcome,'evidence_count',s.evidence_count,
      'blocked_claims',s.blocked_claims) order by s.id) from public.nyay_runtime_steps s where s.execution_id=run_id),'[]'::jsonb))
    into result from public.nyay_runtime_runs r join public.nyay_turn_executions t on t.id=r.execution_id
    where r.execution_id=run_id;
  return result;
end $$;

revoke all on function public.nyay_resume_admit(uuid,uuid,text,jsonb,numeric,jsonb),
  public.nyay_settle_run(uuid,boolean),public.nyay_resume_advance(uuid,uuid,text,jsonb,integer,jsonb,boolean),
  public.nyay_resume_cancel(uuid,uuid,text),public.nyay_record_model_response(uuid,uuid,text,text,jsonb),
  public.nyay_record_step(uuid,uuid,text,integer,integer,text,integer,integer),
  public.nyay_run_observability(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.nyay_resume_admit(uuid,uuid,text,jsonb,numeric,jsonb),
  public.nyay_settle_run(uuid,boolean),public.nyay_resume_advance(uuid,uuid,text,jsonb,integer,jsonb,boolean),
  public.nyay_resume_cancel(uuid,uuid,text),public.nyay_record_model_response(uuid,uuid,text,text,jsonb),
  public.nyay_record_step(uuid,uuid,text,integer,integer,text,integer,integer),
  public.nyay_run_observability(uuid,uuid,text) to service_role;
