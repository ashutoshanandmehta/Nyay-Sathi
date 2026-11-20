-- Package 1 & 2: Reconcile foundation migration history, extend durable cases/documents/actions/contacts,
-- protect editorial roles, and add lease-fenced transactional turn lifecycle RPCs.
-- Android backend only. No dependency on, or migration of, the Vercel demo.

-- 1. Reconcile CLI migration history if the foundation was applied via Dashboard SQL Editor.
do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'supabase_migrations'
      and table_name = 'schema_migrations'
  ) then
    insert into supabase_migrations.schema_migrations (version, name, statements)
    values ('20261119091306', 'android_backend_foundation', array[]::text[])
    on conflict (version) do nothing;
  end if;
end $$;

-- 2. Extend foundation tables for lease-fenced turn execution, durable sequenced SSE events, and staged case patches.
alter table public.nyay_case_memory
  add column if not exists staged_patches jsonb not null default '[]'::jsonb,
  add column if not exists case_proposals jsonb not null default '[]'::jsonb,
  add column if not exists quality_review_consent boolean not null default false;

alter table public.nyay_turn_executions
  add column if not exists lease_token uuid,
  add column if not exists generation integer not null default 1 check (generation > 0),
  add column if not exists user_message_id uuid,
  add column if not exists assistant_message_id uuid,
  add column if not exists case_version integer not null default 0,
  add column if not exists error_detail jsonb;

alter table public.nyay_turn_events
  add column if not exists seq integer not null default 1 check (seq > 0),
  add column if not exists request_id text not null default '',
  add column if not exists block_id text,
  add column if not exists block_revision integer not null default 1 check (block_revision > 0),
  add column if not exists publication_status text not null default 'published'
    check (publication_status in ('published', 'superseded', 'withheld'));

create unique index if not exists nyay_turn_events_execution_seq
  on public.nyay_turn_events(execution_id, seq);

-- 3. BYOK sealed user keys (server-side AEAD ciphertext only; never readable by anon or authenticated clients).
create table if not exists public.nyay_user_keys (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  sealed_key text not null,
  key_hint text not null check (length(key_hint) between 2 and 16),
  algorithm text not null default 'AES-256-GCM-HKDF-SHA256',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.nyay_user_keys enable row level security;
revoke all on table public.nyay_user_keys from public, anon, authenticated;
grant all on table public.nyay_user_keys to service_role;

-- 4. Case documents / evidence manifest with composite case+owner and conversation+owner integrity.
create table if not exists public.nyay_case_documents (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  conversation_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  filename text not null check (length(filename) between 1 and 255),
  mime_type text not null check (length(mime_type) between 3 and 120),
  byte_length integer not null check (byte_length >= 0 and byte_length <= 10485760),
  sha256 text not null check (length(sha256) = 64),
  extraction_status text not null default 'extracted'
    check (extraction_status in ('extracted', 'partial', 'ocr_required', 'user_corrected', 'failed')),
  extracted_text text not null default '',
  consent_status text not null default 'consented'
    check (consent_status in ('consented', 'withheld')),
  storage_mode text not null default 'disclosed_temporary_processing'
    check (storage_mode in ('disclosed_temporary_processing', 'user_drive_manifest', 'client_extracted_only')),
  correction_history jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade,
  foreign key (conversation_id, owner_id) references public.nyay_conversations(id, owner_id) on delete cascade
);
create index if not exists nyay_case_documents_owner_case
  on public.nyay_case_documents(owner_id, case_id, created_at);
create index if not exists nyay_case_documents_owner_conv
  on public.nyay_case_documents(owner_id, conversation_id, created_at);

-- 5. User actions and 4-step submission receipts (kept strictly distinct from official filing or email send).
create table if not exists public.nyay_user_actions (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  conversation_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (length(title) between 2 and 300),
  status text not null default 'completed'
    check (status in ('pending', 'completed', 'skipped')),
  notes text not null default '' check (length(notes) <= 2000),
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade,
  foreign key (conversation_id, owner_id) references public.nyay_conversations(id, owner_id) on delete cascade
);
create index if not exists nyay_user_actions_owner_case
  on public.nyay_user_actions(owner_id, case_id, created_at);

create table if not exists public.nyay_submission_steps (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  conversation_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  target_channel text not null check (length(target_channel) between 2 and 160),
  step text not null
    check (step in ('previewed', 'consented', 'submitted_by_user', 'receipt_captured')),
  draft_id uuid,
  receipt_reference text not null default '' check (length(receipt_reference) <= 200),
  notes text not null default '' check (length(notes) <= 2000),
  created_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade,
  foreign key (conversation_id, owner_id) references public.nyay_conversations(id, owner_id) on delete cascade
);
create index if not exists nyay_submission_steps_owner_case
  on public.nyay_submission_steps(owner_id, case_id, created_at);

-- Apply owner-scoped SELECT RLS on case documents, user actions, and submission steps.
-- Writes go through validated RPCs / backend endpoints so case version and audit invariants hold.
do $$
declare t text;
begin
  foreach t in array array['nyay_case_documents', 'nyay_user_actions', 'nyay_submission_steps'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from public, anon, authenticated', t);
    execute format('grant select on table public.%I to authenticated', t);
    execute format('grant all on table public.%I to service_role', t);
    if not exists (
      select 1 from pg_policies where schemaname = 'public' and tablename = t and policyname = 'owner_select'
    ) then
      execute format(
        'create policy owner_select on public.%I for select to authenticated using ((select auth.uid()) = owner_id)',
        t
      );
    end if;
  end loop;
end $$;

-- 6. Editorial role protection: only provisioned reviewers in nyay_editorial_reviewers can decide propositions.
create table if not exists public.nyay_editorial_reviewers (
  user_id uuid primary key references auth.users(id) on delete cascade,
  reviewer_name text not null check (length(reviewer_name) between 2 and 120),
  bar_enrollment_ref text not null check (length(bar_enrollment_ref) between 3 and 80),
  active boolean not null default true,
  granted_at timestamptz not null default now()
);
alter table public.nyay_editorial_reviewers enable row level security;
revoke all on table public.nyay_editorial_reviewers from public, anon, authenticated;
grant select on table public.nyay_editorial_reviewers to authenticated;
grant all on table public.nyay_editorial_reviewers to service_role;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'nyay_editorial_reviewers' and policyname = 'reviewer_self_select'
  ) then
    create policy reviewer_self_select on public.nyay_editorial_reviewers
      for select to authenticated using ((select auth.uid()) = user_id);
  end if;
end $$;

create table if not exists public.nyay_editorial_propositions (
  item_id text primary key,
  proposition_id text not null check (length(proposition_id) between 4 and 120),
  submitted_by uuid not null references auth.users(id) on delete cascade,
  status text not null default 'pending_editorial_review'
    check (status in ('pending_editorial_review', 'editor_approved', 'superseded', 'rejected')),
  proposal jsonb not null,
  decision jsonb,
  decided_by uuid references public.nyay_editorial_reviewers(user_id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.nyay_editorial_propositions enable row level security;
revoke all on table public.nyay_editorial_propositions from public, anon, authenticated;
grant select on table public.nyay_editorial_propositions to authenticated;
grant all on table public.nyay_editorial_propositions to service_role;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'nyay_editorial_propositions' and policyname = 'editorial_read_authenticated'
  ) then
    create policy editorial_read_authenticated on public.nyay_editorial_propositions
      for select to authenticated using (true);
  end if;
end $$;

create or replace function public.nyay_decide_editorial_proposition(
  p_item_id text,
  p_decision text,
  p_notes text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := auth.uid();
  rev public.nyay_editorial_reviewers;
  updated public.nyay_editorial_propositions;
begin
  if uid is null then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  select * into rev
  from public.nyay_editorial_reviewers
  where user_id = uid and active = true;
  if not found then
    raise exception 'Editorial reviewer role required' using errcode = '42501';
  end if;
  if p_decision not in ('editor_approved', 'superseded', 'rejected') then
    raise exception 'Invalid editorial decision' using errcode = '22023';
  end if;
  update public.nyay_editorial_propositions
  set status = p_decision,
      decided_by = uid,
      decision = jsonb_build_object(
        'reviewer_id', uid,
        'reviewer_name', rev.reviewer_name,
        'bar_enrollment_ref', rev.bar_enrollment_ref,
        'decision', p_decision,
        'notes', coalesce(p_notes, ''),
        'decided_at', now()
      ),
      updated_at = now()
  where item_id = p_item_id
  returning * into updated;
  if not found then
    raise exception 'Editorial item not found' using errcode = 'P0002';
  end if;
  return to_jsonb(updated);
end $$;
revoke all on function public.nyay_decide_editorial_proposition(text, text, text) from public, anon;
grant execute on function public.nyay_decide_editorial_proposition(text, text, text) to authenticated, service_role;

-- 7. Normalized verified contact registry with official provenance and expiry suppression.
create table if not exists public.nyay_verified_contacts (
  id text primary key,
  category text not null,
  jurisdiction text not null default 'India',
  label text not null,
  channel_type text not null check (channel_type in ('phone', 'whatsapp', 'email', 'portal')),
  destination text not null,
  official_source_url text not null,
  checked_at date not null,
  revalidate_after date not null,
  retired boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  check (revalidate_after >= checked_at)
);
alter table public.nyay_verified_contacts enable row level security;
revoke all on table public.nyay_verified_contacts from public, anon, authenticated;
grant select on table public.nyay_verified_contacts to authenticated, service_role;
grant all on table public.nyay_verified_contacts to service_role;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'nyay_verified_contacts' and policyname = 'contacts_select_authenticated'
  ) then
    create policy contacts_select_authenticated on public.nyay_verified_contacts
      for select to authenticated using (not retired);
  end if;
end $$;

insert into public.nyay_verified_contacts (
  id, category, jurisdiction, label, channel_type, destination, official_source_url, checked_at, revalidate_after
) values
  ('india-erss-112', 'physical_safety', 'India', 'Emergency Response Support System (ERSS)', 'phone', '112', 'https://www.mha.gov.in/emergency-response-support-system-erss', '2026-11-07', '2026-11-14'),
  ('india-cyber-1930', 'financial_cyber_fraud', 'India', 'National Cyber-Financial Fraud Helpline', 'phone', '1930', 'https://cybercrime.gov.in/', '2026-11-07', '2026-11-14'),
  ('india-cyber-portal', 'financial_cyber_fraud', 'India', 'National Cyber Crime Reporting Portal', 'portal', 'https://cybercrime.gov.in/', 'https://cybercrime.gov.in/', '2026-11-07', '2026-11-14'),
  ('india-women-181', 'domestic_violence', 'India', 'Women Helpline (All India)', 'phone', '181', 'https://wcd.gov.in/', '2026-11-07', '2026-11-14'),
  ('india-telemanas-14416', 'self_harm', 'India', 'Tele-MANAS Mental Health Helpline', 'phone', '14416', 'https://telemanas.mohfw.gov.in/', '2026-11-07', '2026-11-14'),
  ('india-ambulance-108', 'medical_emergency', 'India', 'Emergency Ambulance Service', 'phone', '108', 'https://www.mha.gov.in/emergency-response-support-system-erss', '2026-11-07', '2026-11-14'),
  ('india-nch-1915', 'consumer', 'India', 'National Consumer Helpline', 'phone', '1915', 'https://consumerhelpline.gov.in/', '2026-11-07', '2026-11-14'),
  ('india-nch-portal', 'consumer', 'India', 'National Consumer Helpline Portal (INGRAM)', 'portal', 'https://consumerhelpline.gov.in/', 'https://consumerhelpline.gov.in/', '2026-11-07', '2026-11-14'),
  ('india-edaakhil-portal', 'consumer', 'India', 'e-Daakhil Consumer Commission Filing Portal', 'portal', 'https://edaakhil.nic.in/', 'https://edaakhil.nic.in/', '2026-11-07', '2026-11-14'),
  ('india-rbi-cms-portal', 'banking', 'India', 'RBI Complaint Management System (Integrated Ombudsman)', 'portal', 'https://cms.rbi.org.in/', 'https://cms.rbi.org.in/', '2026-11-07', '2026-11-14')
on conflict (id) do nothing;

-- 8. Transactional Turn Lifecycle RPCs (service_role only; enforces ownership, payload-hash idempotency,
-- lease recovery without PID checks, and generation/lease_token fencing against stale workers).

create or replace function public.nyay_admit_turn(
  p_owner_id uuid,
  p_conversation_id uuid,
  p_request_id text,
  p_payload_hash text,
  p_user_content text,
  p_lease_seconds integer default 90,
  p_now timestamptz default now()
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_conv public.nyay_conversations;
  v_existing public.nyay_turn_executions;
  v_other_active public.nyay_turn_executions;
  v_user_msg_id uuid;
  v_lease_token uuid := gen_random_uuid();
  v_lease_until timestamptz := p_now + make_interval(secs => greatest(p_lease_seconds, 5));
  v_events jsonb;
begin
  if p_owner_id is null or p_conversation_id is null or coalesce(trim(p_request_id), '') = '' then
    raise exception 'Missing required turn identity parameters' using errcode = '22023';
  end if;

  select * into v_conv
  from public.nyay_conversations
  where id = p_conversation_id and owner_id = p_owner_id
  for update;

  if not found then
    raise exception 'Conversation not found' using errcode = 'P0002';
  end if;

  -- Check if this request_id was already admitted on this conversation.
  select * into v_existing
  from public.nyay_turn_executions
  where conversation_id = p_conversation_id and request_id = p_request_id
  for update;

  if found then
    if v_existing.payload_hash <> p_payload_hash then
      raise exception 'REQUEST_PAYLOAD_CONFLICT: The request ID already belongs to a different message or attachments'
        using errcode = '23505';
    end if;

    if v_existing.status = 'completed' then
      select coalesce(jsonb_agg(to_jsonb(e) order by e.seq), '[]'::jsonb)
      into v_events
      from public.nyay_turn_events e
      where e.execution_id = v_existing.id and e.owner_id = p_owner_id;

      return jsonb_build_object(
        'action', 'replay_completed',
        'execution_id', v_existing.id,
        'case_id', v_conv.case_id,
        'generation', v_existing.generation,
        'result', v_existing.result,
        'events', v_events
      );
    end if;

    if v_existing.status in ('queued', 'running', 'reviewed') and v_existing.lease_expires_at > p_now then
      select coalesce(jsonb_agg(to_jsonb(e) order by e.seq), '[]'::jsonb)
      into v_events
      from public.nyay_turn_events e
      where e.execution_id = v_existing.id and e.owner_id = p_owner_id;

      return jsonb_build_object(
        'action', 'in_progress',
        'execution_id', v_existing.id,
        'case_id', v_conv.case_id,
        'generation', v_existing.generation,
        'events', v_events
      );
    end if;

    -- Before reclaiming an expired/failed/interrupted turn, ensure no OTHER request_id holds an active lease.
    select * into v_other_active
    from public.nyay_turn_executions
    where conversation_id = p_conversation_id
      and request_id <> p_request_id
      and status in ('queued', 'running', 'reviewed')
    for update;

    if found then
      if v_other_active.lease_expires_at > p_now then
        raise exception 'CONVERSATION_BUSY: Another execution is running for this case'
          using errcode = '55P03';
      end if;
      update public.nyay_turn_executions
      set status = 'interrupted',
          lease_token = null,
          updated_at = p_now
      where id = v_other_active.id;
    end if;

    -- Re-acquire lease with incremented generation token (fences any stale worker from the old lease).
    update public.nyay_turn_executions
    set status = 'running',
        generation = v_existing.generation + 1,
        lease_token = v_lease_token,
        lease_expires_at = v_lease_until,
        updated_at = p_now
    where id = v_existing.id
    returning * into v_existing;

    -- Mark non-safety events from the superseded generation as 'superseded' so events from two worker
    -- generations are never spliced together on reconnect, while durable approved safety survives.
    update public.nyay_turn_events
    set publication_status = 'superseded'
    where execution_id = v_existing.id
      and owner_id = p_owner_id
      and kind <> 'safety'
      and publication_status = 'published';

    select id into v_user_msg_id
    from public.nyay_messages
    where conversation_id = p_conversation_id and request_id = p_request_id and role = 'user';

    select coalesce(jsonb_agg(to_jsonb(e) order by e.seq), '[]'::jsonb)
    into v_events
    from public.nyay_turn_events e
    where e.execution_id = v_existing.id
      and e.owner_id = p_owner_id
      and e.publication_status = 'published';

    return jsonb_build_object(
      'action', 'execute',
      'execution_id', v_existing.id,
      'case_id', v_conv.case_id,
      'user_message_id', v_user_msg_id,
      'lease_token', v_lease_token,
      'generation', v_existing.generation,
      'prior_events', v_events
    );
  end if;

  -- Check if any OTHER request_id is currently active on this conversation.
  select * into v_other_active
  from public.nyay_turn_executions
  where conversation_id = p_conversation_id
    and status in ('queued', 'running', 'reviewed')
  for update;

  if found then
    if v_other_active.lease_expires_at > p_now then
      raise exception 'CONVERSATION_BUSY: Another execution is running for this case'
        using errcode = '55P03';
    end if;
    -- Stale lease expired: transition it to interrupted and clear its lease_token so it cannot publish.
    update public.nyay_turn_executions
    set status = 'interrupted',
        lease_token = null,
        updated_at = p_now
    where id = v_other_active.id;
  end if;

  -- Persist user turn idempotently before admitting execution.
  insert into public.nyay_messages (
    conversation_id, owner_id, request_id, role, content, status, created_at
  ) values (
    p_conversation_id, p_owner_id, p_request_id, 'user', p_user_content, 'complete', p_now
  )
  on conflict (conversation_id, request_id, role) do update
    set content = public.nyay_messages.content
  returning id into v_user_msg_id;

  -- Ensure a case memory row exists at version 0.
  insert into public.nyay_case_memory (case_id, owner_id, version, memory, summary, updated_at)
  values (v_conv.case_id, p_owner_id, 0, '{}'::jsonb, '', p_now)
  on conflict (case_id) do nothing;

  insert into public.nyay_turn_executions (
    conversation_id, owner_id, request_id, payload_hash, status,
    lease_token, lease_expires_at, generation, user_message_id, created_at, updated_at
  ) values (
    p_conversation_id, p_owner_id, p_request_id, p_payload_hash, 'running',
    v_lease_token, v_lease_until, 1, v_user_msg_id, p_now, p_now
  )
  returning * into v_existing;

  return jsonb_build_object(
    'action', 'execute',
    'execution_id', v_existing.id,
    'case_id', v_conv.case_id,
    'user_message_id', v_user_msg_id,
    'lease_token', v_lease_token,
    'generation', v_existing.generation,
    'prior_events', '[]'::jsonb
  );
end $$;

create or replace function public.nyay_append_turn_event(
  p_execution_id uuid,
  p_owner_id uuid,
  p_lease_token uuid,
  p_kind text,
  p_payload jsonb,
  p_block_id text default null,
  p_block_revision integer default 1,
  p_publication_status text default 'published'
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_exec public.nyay_turn_executions;
  v_next_seq integer;
  v_inserted public.nyay_turn_events;
begin
  select * into v_exec
  from public.nyay_turn_executions
  where id = p_execution_id and owner_id = p_owner_id
  for update;

  if not found then
    raise exception 'Turn execution not found' using errcode = 'P0002';
  end if;

  if v_exec.lease_token is distinct from p_lease_token or v_exec.status not in ('running', 'reviewed') then
    raise exception 'STALE_WORKER_FENCED: Turn lease token is no longer active' using errcode = '40001';
  end if;

  select coalesce(max(seq), 0) + 1 into v_next_seq
  from public.nyay_turn_events
  where execution_id = p_execution_id;

  insert into public.nyay_turn_events (
    execution_id, owner_id, seq, request_id, kind, block_id, block_revision, publication_status, payload
  ) values (
    p_execution_id, p_owner_id, v_next_seq, v_exec.request_id, p_kind,
    p_block_id, coalesce(p_block_revision, 1), coalesce(p_publication_status, 'published'), p_payload
  )
  returning * into v_inserted;

  return to_jsonb(v_inserted);
end $$;

create or replace function public.nyay_commit_turn(
  p_execution_id uuid,
  p_owner_id uuid,
  p_lease_token uuid,
  p_expected_case_version integer,
  p_new_case_version integer,
  p_memory jsonb,
  p_summary text,
  p_staged_patches jsonb,
  p_case_proposals jsonb,
  p_assistant_content text,
  p_assistant_metadata jsonb,
  p_drafts jsonb default '[]'::jsonb,
  p_result jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_exec public.nyay_turn_executions;
  v_conv public.nyay_conversations;
  v_mem public.nyay_case_memory;
  v_assistant_msg public.nyay_messages;
  v_draft jsonb;
  v_created_draft_ids jsonb := '[]'::jsonb;
  v_draft_id uuid;
  v_next_seq integer;
  v_final_result jsonb;
begin
  select * into v_exec
  from public.nyay_turn_executions
  where id = p_execution_id and owner_id = p_owner_id
  for update;

  if not found then
    raise exception 'Turn execution not found' using errcode = 'P0002';
  end if;

  if v_exec.lease_token is distinct from p_lease_token or v_exec.status not in ('running', 'reviewed') then
    raise exception 'STALE_WORKER_FENCED: Turn lease token is no longer active' using errcode = '40001';
  end if;

  select * into v_conv
  from public.nyay_conversations
  where id = v_exec.conversation_id and owner_id = p_owner_id
  for update;

  insert into public.nyay_case_memory (case_id, owner_id, version, memory, summary)
  values (v_conv.case_id, p_owner_id, 0, '{}'::jsonb, '')
  on conflict (case_id) do nothing;

  select * into v_mem
  from public.nyay_case_memory
  where case_id = v_conv.case_id and owner_id = p_owner_id
  for update;

  if v_mem.version <> p_expected_case_version then
    raise exception 'CASE_VERSION_CONFLICT: Expected case version %, found %',
      p_expected_case_version, v_mem.version
      using errcode = '40001';
  end if;

  if p_new_case_version < p_expected_case_version then
    raise exception 'Invalid target case version' using errcode = '22023';
  end if;

  update public.nyay_case_memory
  set version = p_new_case_version,
      memory = coalesce(p_memory, v_mem.memory),
      summary = coalesce(p_summary, v_mem.summary),
      staged_patches = coalesce(p_staged_patches, v_mem.staged_patches),
      case_proposals = coalesce(p_case_proposals, v_mem.case_proposals),
      updated_at = now()
  where case_id = v_conv.case_id and owner_id = p_owner_id;

  if p_new_case_version > p_expected_case_version then
    update public.nyay_drafts
    set status = 'stale',
        updated_at = now()
    where case_id = v_conv.case_id
      and owner_id = p_owner_id
      and case_version < p_new_case_version
      and status <> 'stale';
  end if;

  if jsonb_typeof(p_drafts) = 'array' then
    for v_draft in select * from jsonb_array_elements(p_drafts) loop
      insert into public.nyay_drafts (
        case_id, owner_id, title, content, version, case_version, status
      ) values (
        v_conv.case_id,
        p_owner_id,
        coalesce(nullif(trim(v_draft->>'title'), ''), 'Prepared Draft'),
        coalesce(v_draft->>'content', ''),
        1,
        p_new_case_version,
        coalesce(v_draft->>'status', 'preliminary')
      )
      returning id into v_draft_id;
      v_created_draft_ids := v_created_draft_ids || to_jsonb(v_draft_id::text);
    end loop;
  end if;

  insert into public.nyay_messages (
    conversation_id, owner_id, request_id, role, content, status, metadata
  ) values (
    v_exec.conversation_id,
    p_owner_id,
    v_exec.request_id,
    'assistant',
    p_assistant_content,
    'complete',
    coalesce(p_assistant_metadata, '{}'::jsonb)
  )
  on conflict (conversation_id, request_id, role) do update
    set content = excluded.content,
        status = excluded.status,
        metadata = excluded.metadata
  returning * into v_assistant_msg;

  update public.nyay_conversations
  set updated_at = now()
  where id = v_exec.conversation_id and owner_id = p_owner_id;

  update public.nyay_cases
  set updated_at = now()
  where id = v_conv.case_id and owner_id = p_owner_id;

  v_final_result := coalesce(p_result, '{}'::jsonb) || jsonb_build_object(
    'assistant_message', to_jsonb(v_assistant_msg),
    'case_version', p_new_case_version,
    'created_draft_ids', v_created_draft_ids
  );

  select coalesce(max(seq), 0) + 1 into v_next_seq
  from public.nyay_turn_events
  where execution_id = p_execution_id;

  insert into public.nyay_turn_events (
    execution_id, owner_id, seq, request_id, kind, publication_status, payload
  ) values (
    p_execution_id, p_owner_id, v_next_seq, v_exec.request_id, 'result', 'published', v_final_result
  );

  update public.nyay_turn_executions
  set status = 'completed',
      assistant_message_id = v_assistant_msg.id,
      case_version = p_new_case_version,
      reviewed_result = v_final_result,
      result = v_final_result,
      lease_token = null,
      updated_at = now()
  where id = p_execution_id and owner_id = p_owner_id;

  return v_final_result;
end $$;

revoke all on function public.nyay_admit_turn(uuid, uuid, text, text, text, integer, timestamptz) from public, anon, authenticated;
grant execute on function public.nyay_admit_turn(uuid, uuid, text, text, text, integer, timestamptz) to service_role;

revoke all on function public.nyay_append_turn_event(uuid, uuid, uuid, text, jsonb, text, integer, text) from public, anon, authenticated;
grant execute on function public.nyay_append_turn_event(uuid, uuid, uuid, text, jsonb, text, integer, text) to service_role;

revoke all on function public.nyay_commit_turn(uuid, uuid, uuid, integer, integer, jsonb, text, jsonb, jsonb, text, jsonb, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.nyay_commit_turn(uuid, uuid, uuid, integer, integer, jsonb, text, jsonb, jsonb, text, jsonb, jsonb, jsonb) to service_role;
