-- Android backend only. No dependency on, or migration of, the Vercel demo.
create table public.nyay_cases (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'New case' check (length(title) between 1 and 80),
  status text not null default 'intake',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id)
);
create index nyay_cases_owner_updated on public.nyay_cases(owner_id, updated_at desc);

create table public.nyay_conversations (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'New case' check (length(title) between 1 and 80),
  language text not null default 'en' check (language in ('en', 'hi', 'hinglish')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(id, owner_id),
  foreign key(case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade
);
create index nyay_conversations_owner_updated on public.nyay_conversations(owner_id, updated_at desc);
create index nyay_conversations_case_owner on public.nyay_conversations(case_id, owner_id);

-- These records are read by the owner, written by trusted backend operations.
-- Clients cannot fabricate an assistant reply or a review/approval receipt.
create table public.nyay_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null,
  owner_id uuid not null,
  request_id text not null,
  role text not null check(role in ('user', 'assistant', 'system')),
  content text not null,
  status text not null default 'complete',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(conversation_id, request_id, role),
  foreign key(conversation_id, owner_id) references public.nyay_conversations(id, owner_id) on delete cascade
);
create index nyay_messages_owner_thread_time on public.nyay_messages(owner_id, conversation_id, created_at);

create table public.nyay_case_memory (
  case_id uuid primary key,
  owner_id uuid not null,
  version integer not null default 0 check(version >= 0),
  memory jsonb not null default '{}'::jsonb,
  summary text not null default '',
  updated_at timestamptz not null default now(),
  foreign key(case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade
);
create index nyay_memory_owner on public.nyay_case_memory(owner_id);

create table public.nyay_drafts (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  owner_id uuid not null,
  title text not null,
  content text not null,
  version integer not null default 1 check(version > 0),
  case_version integer not null default 0,
  status text not null default 'preliminary',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key(case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade
);
create index nyay_drafts_owner_case on public.nyay_drafts(owner_id, case_id);

create table public.nyay_turn_executions (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null,
  owner_id uuid not null,
  request_id text not null,
  payload_hash text not null,
  status text not null check(status in ('queued','running','reviewed','completed','failed','interrupted')),
  lease_expires_at timestamptz,
  reviewed_result jsonb,
  result jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(conversation_id, request_id),
  unique(id, owner_id),
  foreign key(conversation_id, owner_id) references public.nyay_conversations(id, owner_id) on delete cascade
);
create index nyay_turns_owner_thread on public.nyay_turn_executions(owner_id, conversation_id);
create unique index nyay_one_running_turn on public.nyay_turn_executions(conversation_id)
  where status in ('queued','running','reviewed');

create table public.nyay_turn_events (
  id bigint generated always as identity primary key,
  execution_id uuid not null,
  owner_id uuid not null,
  kind text not null check(kind in ('progress','safety','answer_block','result','error')),
  payload jsonb not null,
  created_at timestamptz not null default now(),
  foreign key(execution_id, owner_id) references public.nyay_turn_executions(id, owner_id) on delete cascade
);
create index nyay_turn_events_owner_execution_id on public.nyay_turn_events(owner_id, execution_id, id);

do $$
declare table_name text;
begin
  foreach table_name in array array['nyay_cases','nyay_conversations','nyay_messages','nyay_case_memory','nyay_drafts','nyay_turn_executions','nyay_turn_events'] loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on table public.%I from anon, authenticated', table_name);
    execute format('grant select on table public.%I to authenticated', table_name);
    execute format('grant all on table public.%I to service_role', table_name);
    execute format('create policy owner_select on public.%I for select to authenticated using ((select auth.uid()) = owner_id)', table_name);
  end loop;
  foreach table_name in array array['nyay_cases','nyay_conversations'] loop
    execute format('grant insert, update, delete on table public.%I to authenticated', table_name);
    execute format('create policy owner_insert on public.%I for insert to authenticated with check ((select auth.uid()) = owner_id)', table_name);
    execute format('create policy owner_update on public.%I for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id)', table_name);
    execute format('create policy owner_delete on public.%I for delete to authenticated using ((select auth.uid()) = owner_id)', table_name);
  end loop;
end $$;

-- SECURITY INVOKER: every insert and parent lookup still obeys RLS.
create function public.nyay_create_conversation(p_language text default 'en', p_case_id uuid default null)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare uid uuid := auth.uid(); cid uuid := p_case_id; result public.nyay_conversations;
begin
  if uid is null then raise exception 'Authentication required' using errcode = '42501'; end if;
  if p_language not in ('en','hi','hinglish') or p_language is null then
    raise exception 'Unsupported language' using errcode = '22023';
  end if;
  if cid is null then
    insert into public.nyay_cases(owner_id) values(uid) returning id into cid;
  elsif not exists(select 1 from public.nyay_cases where id = cid and owner_id = uid) then
    raise exception 'Case not found' using errcode = '42501';
  end if;
  insert into public.nyay_conversations(case_id, owner_id, language)
    values(cid, uid, p_language) returning * into result;
  return to_jsonb(result);
end $$;
revoke all on function public.nyay_create_conversation(text, uuid) from public, anon;
grant execute on function public.nyay_create_conversation(text, uuid) to authenticated;
grant usage, select on sequence public.nyay_turn_events_id_seq to service_role;
