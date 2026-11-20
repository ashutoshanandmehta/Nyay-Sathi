-- Private checkpoint and transactional outbox for existing turn executions.
create table public.nyay_turn_work (
  execution_id uuid primary key,
  owner_id uuid not null,
  stage text not null default 'prepare',
  checkpoint jsonb not null,
  due_at timestamptz not null default now(),
  lease_token uuid,
  lease_until timestamptz,
  generation integer not null default 0,
  attempts integer not null default 0,
  foreign key (execution_id, owner_id) references public.nyay_turn_executions(id, owner_id) on delete cascade
);
create index nyay_turn_work_due on public.nyay_turn_work(due_at, execution_id);
alter table public.nyay_turn_work enable row level security;
revoke all on public.nyay_turn_work from public, anon, authenticated;
grant select, insert, update, delete on public.nyay_turn_work to service_role;

create function public.nyay_resume_admit(p_owner uuid, p_chat uuid, p_request text, p_payload jsonb, p_reserve numeric)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  turn public.nyay_turn_executions;
  message_id uuid;
  signature text := encode(sha256(convert_to(p_payload::text, 'UTF8')), 'hex');
  reserved integer;
begin
  perform 1 from public.nyay_conversations where id=p_chat and owner_id=p_owner for update;
  if not found then return '{"error":"not_found"}'; end if;
  select * into turn from public.nyay_turn_executions where conversation_id=p_chat and request_id=p_request;
  if found then
    if turn.payload_hash<>signature then return '{"error":"request_conflict"}'; end if;
    return jsonb_build_object('execution_id',turn.id,'status',turn.status);
  end if;
  if exists(select 1 from public.nyay_turn_executions where conversation_id=p_chat and status in ('queued','running','reviewed')) then
    return '{"error":"active_turn"}';
  end if;
  if p_reserve is null or p_reserve <= 0 then return '{"error":"budget"}'; end if;
  -- Serialized project cap plus the existing owner budget reservation.
  perform pg_advisory_xact_lock(81923514);
  if (select coalesce(sum(estimated_spend_usd),0) from public.nyay_usage_budgets where window_date=current_date) + p_reserve > 5 then
    return '{"error":"budget"}';
  end if;
  insert into public.nyay_usage_budgets(owner_id,window_date,requests_count,estimated_spend_usd)
  values(p_owner,current_date,1,p_reserve)
  on conflict(owner_id,window_date) do update
  set requests_count=nyay_usage_budgets.requests_count+1,
      estimated_spend_usd=nyay_usage_budgets.estimated_spend_usd+p_reserve
  where nyay_usage_budgets.requests_count < nyay_usage_budgets.max_daily_requests
    and nyay_usage_budgets.estimated_spend_usd+p_reserve <= nyay_usage_budgets.max_daily_spend_usd
  returning requests_count into reserved;
  if reserved is null then return '{"error":"budget"}'; end if;
  insert into public.nyay_messages(conversation_id,owner_id,request_id,role,content)
  values(p_chat,p_owner,p_request,'user',p_payload->>'content') returning id into message_id;
  insert into public.nyay_turn_executions(conversation_id,owner_id,request_id,payload_hash,status,user_message_id)
  values(p_chat,p_owner,p_request,signature,'queued',message_id) returning * into turn;
  insert into public.nyay_turn_work(execution_id,owner_id,checkpoint)
  values(turn.id,p_owner,jsonb_build_object('input',p_payload));
  insert into public.nyay_turn_events(execution_id,owner_id,request_id,seq,kind,payload)
  values(turn.id,p_owner,p_request,1,'progress','{"stage":"accepted","status":"queued"}');
  return jsonb_build_object('execution_id',turn.id,'status',turn.status);
end $$;

create function public.nyay_resume_claim()
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  work public.nyay_turn_work;
begin
  select * into work from public.nyay_turn_work
  where due_at<=clock_timestamp() and (lease_until is null or lease_until<=clock_timestamp())
  order by due_at, execution_id limit 1 for update skip locked;
  if not found then return null; end if;
  update public.nyay_turn_work set lease_token=gen_random_uuid(), lease_until=clock_timestamp()+interval '35 seconds',
    generation=generation+1, attempts=attempts+1 where execution_id=work.execution_id returning * into work;
  if work.stage<>'cancel_provider' then
    update public.nyay_turn_executions set status='running', lease_token=work.lease_token, lease_expires_at=work.lease_until,
      generation=work.generation where id=work.execution_id;
  end if;
  return to_jsonb(work);
end $$;

create function public.nyay_resume_advance(p_id uuid,p_token uuid,p_stage text,p_state jsonb,p_delay integer,p_event jsonb default null,p_keep_lease boolean default false)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare
  work public.nyay_turn_work;
  turn public.nyay_turn_executions;
  next_seq integer;
  case_row public.nyay_cases;
begin
  select * into work from public.nyay_turn_work where execution_id=p_id for update;
  if not found or work.lease_token is distinct from p_token or work.lease_until<=clock_timestamp() or p_token is null then return false; end if;
  select * into turn from public.nyay_turn_executions where id=p_id for update;
  if work.stage='cancel_provider' and p_stage not in ('cancel_provider','discard') then return false; end if;
  if p_stage='publish' then
    if work.stage<>'ready' or turn.status<>'running' then return false; end if;
    select c.* into case_row from public.nyay_cases c
    join public.nyay_conversations v on v.case_id=c.id and v.owner_id=c.owner_id
    where v.id=turn.conversation_id and v.owner_id=turn.owner_id for update of v, c;
    if nullif(case_row.jurisdiction,'India') is distinct from p_state->>'expected_region'
       or case_row.incident_date::text is distinct from p_state->>'expected_incident_date' then
      raise exception 'Case applicability changed during review' using errcode='40001';
    end if;
    perform 1 from public.nyay_case_documents
    where case_id=case_row.id and owner_id=turn.owner_id
      and consent_status='consented'
      and id::text in (select jsonb_array_elements_text(p_state->'used_attachment_ids'))
    for update;
    if (select count(*) from public.nyay_case_documents
      where case_id=case_row.id and owner_id=turn.owner_id and consent_status='consented'
        and id::text in (select jsonb_array_elements_text(p_state->'used_attachment_ids')))
        <> jsonb_array_length(p_state->'used_attachment_ids') then
      raise exception 'Attachment consent changed during review' using errcode='40001';
    end if;
    -- Only server-generated verified blocks enter the same transaction as the final result.
    for p_event in select jsonb_build_object('block',value) from jsonb_array_elements(p_state->'metadata'->'resolution_blocks') loop
      perform public.nyay_append_turn_event(p_id,turn.owner_id,p_token,'answer_block',p_event,p_event->'block'->>'block_id',1,'published');
    end loop;
    perform public.nyay_commit_turn(p_id,turn.owner_id,p_token,
      (p_state->>'expected_version')::integer,(p_state->'memory'->>'version')::integer,
      p_state->'memory',null,p_state->'staged',p_state->'proposals',p_state->>'content',
      p_state->'metadata',p_state->'drafts',p_state->'result');
    delete from public.nyay_turn_work where execution_id=p_id;
    return true;
  end if;
  if p_stage='failed' then
    update public.nyay_turn_executions set status='failed',lease_token=null,lease_expires_at=null,error_detail=p_event where id=p_id;
    delete from public.nyay_turn_work where execution_id=p_id;
  elsif p_stage='discard' then
    delete from public.nyay_turn_work where execution_id=p_id;
  else
    update public.nyay_turn_work set stage=p_stage, checkpoint=p_state, due_at=clock_timestamp()+make_interval(secs=>p_delay),
      attempts=case when stage=p_stage then attempts else 0 end,
      lease_token=case when p_keep_lease then lease_token end, lease_until=case when p_keep_lease then lease_until end
    where execution_id=p_id;
    if not p_keep_lease then update public.nyay_turn_executions set lease_token=null,lease_expires_at=null where id=p_id; end if;
  end if;
  if p_event is not null then
    select coalesce(max(seq),0)+1 into next_seq from public.nyay_turn_events where execution_id=p_id;
    insert into public.nyay_turn_events(execution_id,owner_id,request_id,seq,kind,payload)
    values(p_id,turn.owner_id,turn.request_id,next_seq,case when p_stage='failed' then 'error' when p_event->>'type'='safety' then 'safety' else 'progress' end,p_event);
  end if;
  return true;
end $$;

create function public.nyay_resume_cancel(p_owner uuid,p_chat uuid,p_request text)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare
  work public.nyay_turn_work;
  turn public.nyay_turn_executions;
  next_seq integer;
begin
  select * into turn from public.nyay_turn_executions where owner_id=p_owner and conversation_id=p_chat and request_id=p_request;
  if not found then return false; end if;
  if turn.status='interrupted' then return true; end if;
  select * into work from public.nyay_turn_work where execution_id=turn.id for update;
  if not found then return false; end if;
  select * into turn from public.nyay_turn_executions where id=work.execution_id for update;
  if turn.status='interrupted' then return true; end if;
  update public.nyay_turn_executions set status='interrupted',lease_token=null,lease_expires_at=null,
    error_detail='{"detail":"Turn cancelled.","code":"cancelled"}' where id=turn.id;
  if work.checkpoint ? 'responseId' or work.stage='submitting' then
    update public.nyay_turn_work set stage='cancel_provider',due_at=clock_timestamp(),lease_token=null,lease_until=null,attempts=0
    where execution_id=turn.id;
  else
    delete from public.nyay_turn_work where execution_id=turn.id;
  end if;
  select coalesce(max(seq),0)+1 into next_seq from public.nyay_turn_events where execution_id=turn.id;
  insert into public.nyay_turn_events(execution_id,owner_id,request_id,seq,kind,payload)
  values(turn.id,p_owner,p_request,next_seq,'error','{"detail":"Turn cancelled.","code":"cancelled"}');
  return true;
end $$;

-- Only the verified webhook handler can wake a job. Polling covers early/lost deliveries.
create table public.nyay_turn_webhook_receipts (
  delivery_id text primary key,
  received_at timestamptz not null default now()
);
alter table public.nyay_turn_webhook_receipts enable row level security;
revoke all on public.nyay_turn_webhook_receipts from public, anon, authenticated;
grant select, insert, delete on public.nyay_turn_webhook_receipts to service_role;
create index nyay_turn_work_response on public.nyay_turn_work ((checkpoint->>'responseId'))
where stage='collect';
create function public.nyay_resume_wake(p_delivery text,p_response text)
returns text language plpgsql security invoker set search_path = '' as $$
begin
  if exists(select 1 from public.nyay_turn_webhook_receipts where delivery_id=p_delivery) then return 'duplicate'; end if;
  update public.nyay_turn_work set due_at=least(due_at,clock_timestamp())
  where stage='collect' and checkpoint->>'responseId'=p_response;
  if not found then return 'unknown'; end if;
  insert into public.nyay_turn_webhook_receipts(delivery_id) values(p_delivery) on conflict do nothing;
  return 'woken';
end $$;

revoke all on function public.nyay_resume_admit(uuid,uuid,text,jsonb,numeric),
 public.nyay_resume_claim(), public.nyay_resume_advance(uuid,uuid,text,jsonb,integer,jsonb,boolean),
 public.nyay_resume_cancel(uuid,uuid,text), public.nyay_resume_wake(text,text) from public, anon, authenticated;
grant execute on function public.nyay_resume_admit(uuid,uuid,text,jsonb,numeric),
 public.nyay_resume_claim(), public.nyay_resume_advance(uuid,uuid,text,jsonb,integer,jsonb,boolean),
 public.nyay_resume_cancel(uuid,uuid,text), public.nyay_resume_wake(text,text) to service_role;

-- A verified terminal webhook may recover a lost POST acknowledgement. The
-- caller first reads the response with the same provider account and verifies its intent metadata.
create function public.nyay_resume_reconcile(p_intent uuid,p_response text)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare work public.nyay_turn_work;
begin
  select * into work from public.nyay_turn_work
  where stage in ('submitting','cancel_provider') and checkpoint->>'intent'=p_intent::text for update;
  if not found then return true; end if;
  if work.lease_until>clock_timestamp() then return false; end if;
  update public.nyay_turn_work set stage=case when stage='submitting' then 'collect' else stage end,
    checkpoint=checkpoint || jsonb_build_object('responseId',p_response),due_at=clock_timestamp(),
    lease_token=null,lease_until=null,attempts=0 where execution_id=work.execution_id;
  return true;
end $$;
create index nyay_turn_work_intent on public.nyay_turn_work ((checkpoint->>'intent'))
where stage in ('submitting','cancel_provider');
revoke all on function public.nyay_resume_reconcile(uuid,text) from public, anon, authenticated;
grant execute on function public.nyay_resume_reconcile(uuid,text) to service_role;

create function public.nyay_resume_record_delivery(p_delivery text)
returns void language sql security invoker set search_path = '' as $$
  insert into public.nyay_turn_webhook_receipts(delivery_id) values(p_delivery) on conflict do nothing
$$;
revoke all on function public.nyay_resume_record_delivery(text) from public, anon, authenticated;
grant execute on function public.nyay_resume_record_delivery(text) to service_role;
