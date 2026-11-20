-- Packages 4, 5, 6 & 7: Core Consumer/Fraud Workflows, Google Drive Evidence Manifests,
-- Gmail Reviewed & Payload-Bound Approved Communications, Separate OAuth Secret Storage,
-- Versioned Legal Knowledge & Transitional Relations, and Project/User Spend Budgets.
-- Android backend only. No dependency on, or migration of, the Vercel demo.

-- 1. Reconcile prior migration history idempotently if applied via Dashboard SQL Editor.
do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'supabase_migrations'
      and table_name = 'schema_migrations'
  ) then
    insert into supabase_migrations.schema_migrations (version, name, statements)
    values
      ('20261119091306', 'android_backend_foundation', array[]::text[]),
      ('20261119120000', 'package1_auth_durable_cases_and_runtime', array[]::text[])
    on conflict (version) do nothing;
  end if;
end $$;

-- 2. Extend nyay_cases with domain, lifecycle_projection (keeping submissions, promises,
-- processed_refunds, remedy_receipt, and closure distinct), and incident_date.
alter table public.nyay_cases
  add column if not exists domain text not null default 'unknown',
  add column if not exists incident_date date,
  add column if not exists jurisdiction text not null default 'India',
  add column if not exists lifecycle_state jsonb not null default '{
    "submissions": [],
    "promises": [],
    "processed_refunds": [],
    "remedy_receipt": null,
    "closure": "open"
  }'::jsonb;

-- 3. Provider Connections (client-readable status/scopes/opt-in) & Separate OAuth Secrets (service_role only).
create table if not exists public.nyay_provider_connections (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  provider text not null check (provider in ('google_drive', 'google_gmail')),
  provider_account_email text not null check (length(provider_account_email) between 3 and 254),
  provider_user_id text not null check (length(provider_user_id) between 1 and 128),
  granted_scopes text[] not null default '{}'::text[],
  status text not null default 'connected'
    check (status in ('connected', 'expired', 'revoked', 'error')),
  reply_monitoring_opted_in boolean not null default false,
  last_verified_at timestamptz not null default now(),
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_id, provider),
  unique (id, owner_id)
);
create index if not exists nyay_provider_connections_owner
  on public.nyay_provider_connections(owner_id, provider);

create table if not exists public.nyay_provider_secrets (
  connection_id uuid primary key references public.nyay_provider_connections(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  sealed_access_token text not null,
  sealed_refresh_token text,
  token_expires_at timestamptz,
  algorithm text not null default 'AES-256-GCM-HKDF-SHA256',
  updated_at timestamptz not null default now()
);

alter table public.nyay_provider_secrets enable row level security;
revoke all on table public.nyay_provider_secrets from public, anon, authenticated;
grant all on table public.nyay_provider_secrets to service_role;

-- 4. Google Drive Case Folders & Evidence Manifests (Package 5).
create table if not exists public.nyay_drive_case_folders (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  connection_id uuid not null,
  provider_account_email text not null,
  drive_folder_id text not null check (length(drive_folder_id) between 3 and 200),
  opaque_folder_name text not null
    check (opaque_folder_name ~ '^NyaySaathi-Case-[a-z0-9]{8,24}$'),
  sync_status text not null default 'synced'
    check (sync_status in ('synced', 'moved', 'deleted', 'revoked')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (case_id, owner_id),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade,
  foreign key (connection_id, owner_id) references public.nyay_provider_connections(id, owner_id) on delete cascade
);
create index if not exists nyay_drive_case_folders_owner_case
  on public.nyay_drive_case_folders(owner_id, case_id);

create table if not exists public.nyay_drive_manifests (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  folder_id uuid,
  document_id uuid,
  provider_account_email text not null,
  drive_file_id text not null check (length(drive_file_id) between 3 and 200),
  filename text not null check (length(filename) between 1 and 255),
  mime_type text not null check (length(mime_type) between 3 and 120),
  byte_length integer not null check (byte_length >= 0 and byte_length <= 26214400),
  sha256 text not null check (length(sha256) = 64),
  evidence_type text not null default 'supporting_document',
  provenance text not null default 'user_uploaded_original'
    check (provenance in ('user_uploaded_original', 'user_selected_drive_file', 'local_v2_disclosed_explicit')),
  sync_status text not null default 'synced'
    check (sync_status in ('synced', 'moved', 'deleted', 'revoked', 'local_only')),
  original_preserved boolean not null default true,
  web_view_link text,
  status_explanation text not null default '',
  last_reconciled_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (case_id, owner_id, sha256),
  unique (case_id, owner_id, drive_file_id),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade
);
create index if not exists nyay_drive_manifests_owner_case
  on public.nyay_drive_manifests(owner_id, case_id, created_at);

-- 5. Gmail Selected Evidence Messages, Payload-Bound Send Approvals & Durable Dispatches (Package 6).
create table if not exists public.nyay_gmail_evidence_messages (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  gmail_message_id text not null check (length(gmail_message_id) between 2 and 160),
  gmail_thread_id text not null check (length(gmail_thread_id) between 2 and 160),
  provider_account_email text not null,
  sender text not null,
  recipient text not null,
  subject text not null,
  snippet text not null default '',
  body_text text not null default '',
  received_at timestamptz,
  untrusted_instruction_flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (case_id, owner_id, gmail_message_id),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade
);
create index if not exists nyay_gmail_evidence_owner_case
  on public.nyay_gmail_evidence_messages(owner_id, case_id, created_at);

create table if not exists public.nyay_gmail_approvals (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  conversation_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  provider_account_email text not null,
  sender_email text not null,
  to_recipients text[] not null check (cardinality(to_recipients) >= 1),
  cc_recipients text[] not null default '{}'::text[],
  bcc_recipients text[] not null default '{}'::text[],
  subject text not null check (length(subject) between 1 and 300),
  body text not null check (length(body) between 1 and 100000),
  selected_attachment_ids text[] not null default '{}'::text[],
  reply_thread_id text,
  payload_hash text not null check (length(payload_hash) = 64),
  version integer not null default 1 check (version > 0),
  status text not null default 'approved'
    check (status in ('approved', 'invalidated', 'dispatched', 'expired')),
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade,
  foreign key (conversation_id, owner_id) references public.nyay_conversations(id, owner_id) on delete cascade
);
create index if not exists nyay_gmail_approvals_owner_case
  on public.nyay_gmail_approvals(owner_id, case_id, created_at desc);

create table if not exists public.nyay_gmail_dispatches (
  id uuid primary key default gen_random_uuid(),
  approval_id uuid not null unique,
  case_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  payload_hash text not null check (length(payload_hash) = 64),
  provider_account_email text not null,
  dispatch_status text not null
    check (dispatch_status in (
      'dispatching',
      'sent_confirmed',
      'ambiguous_timeout_needs_reconciliation',
      'reconciled_sent',
      'reconciled_not_sent',
      'failed'
    )),
  gmail_message_id text,
  gmail_thread_id text,
  event_classification text not null default 'provider_email_sent_not_official_registration'
    check (event_classification = 'provider_email_sent_not_official_registration'),
  reconciliation_notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (approval_id, owner_id) references public.nyay_gmail_approvals(id, owner_id) on delete cascade,
  foreign key (case_id, owner_id) references public.nyay_cases(id, owner_id) on delete cascade
);
create index if not exists nyay_gmail_dispatches_owner_case
  on public.nyay_gmail_dispatches(owner_id, case_id, created_at desc);

-- 6. User & Project Request / Spend Budgets (Section 7 operational enforcement).
create table if not exists public.nyay_usage_budgets (
  owner_id uuid not null references auth.users(id) on delete cascade,
  window_date date not null default current_date,
  requests_count integer not null default 0 check (requests_count >= 0),
  provider_calls_count integer not null default 0 check (provider_calls_count >= 0),
  total_tokens_used integer not null default 0 check (total_tokens_used >= 0),
  estimated_spend_usd numeric(10, 4) not null default 0 check (estimated_spend_usd >= 0),
  max_daily_requests integer not null default 200 check (max_daily_requests > 0),
  max_daily_spend_usd numeric(10, 4) not null default 5.0000 check (max_daily_spend_usd > 0),
  updated_at timestamptz not null default now(),
  primary key (owner_id, window_date)
);

-- Apply owner-scoped SELECT RLS on all new private owner-scoped tables.
do $$
declare t text;
begin
  foreach t in array array[
    'nyay_provider_connections',
    'nyay_drive_case_folders',
    'nyay_drive_manifests',
    'nyay_gmail_evidence_messages',
    'nyay_gmail_approvals',
    'nyay_gmail_dispatches',
    'nyay_usage_budgets'
  ] loop
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

-- 7. Versioned Legal Provisions, Transitional Relations & Cache Invalidation Epoch (Package 7).
create table if not exists public.nyay_legal_provisions (
  provision_id text primary key,
  act_id text not null,
  act_title text not null,
  section_locator text not null,
  domain text not null default 'general',
  jurisdiction text not null default 'India',
  version_label text not null default 'v1',
  content_hash text not null,
  summary_text text not null,
  exact_text text not null,
  effective_from date,
  effective_until date,
  repealed_or_superseded boolean not null default false,
  transitional_rule text not null default '',
  known_exceptions jsonb not null default '[]'::jsonb,
  review_state text not null default 'source_verified_pending_legal_review'
    check (review_state in (
      'source_verified_pending_legal_review',
      'qualified_legal_reviewed',
      'amended_cache_invalidated',
      'retired'
    )),
  canonical_url text not null,
  last_checked_at timestamptz not null default now(),
  cache_epoch integer not null default 1 check (cache_epoch > 0)
);

alter table public.nyay_legal_provisions enable row level security;
revoke all on table public.nyay_legal_provisions from public, anon, authenticated;
grant select on table public.nyay_legal_provisions to authenticated, service_role;
grant all on table public.nyay_legal_provisions to service_role;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'nyay_legal_provisions' and policyname = 'legal_provisions_select_authenticated'
  ) then
    create policy legal_provisions_select_authenticated on public.nyay_legal_provisions
      for select to authenticated using (review_state <> 'retired');
  end if;
end $$;

create table if not exists public.nyay_legal_relations (
  id text primary key,
  from_provision_id text not null references public.nyay_legal_provisions(provision_id) on delete cascade,
  to_provision_id text not null references public.nyay_legal_provisions(provision_id) on delete cascade,
  relation_type text not null
    check (relation_type in ('superseded_by', 'amended_by', 'transitional_saving', 'state_amendment')),
  cutoff_date date,
  procedural_rule text not null
);

alter table public.nyay_legal_relations enable row level security;
revoke all on table public.nyay_legal_relations from public, anon, authenticated;
grant select on table public.nyay_legal_relations to authenticated, service_role;
grant all on table public.nyay_legal_relations to service_role;
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'nyay_legal_relations' and policyname = 'legal_relations_select_authenticated'
  ) then
    create policy legal_relations_select_authenticated on public.nyay_legal_relations
      for select to authenticated using (true);
  end if;
end $$;

-- Seed core historical/current transitional legal provisions (IPC/CrPC -> BNS/BNSS, CPA 2019, RBI Directions).
insert into public.nyay_legal_provisions (
  provision_id, act_id, act_title, section_locator, domain, jurisdiction, version_label,
  content_hash, summary_text, exact_text, effective_from, effective_until,
  repealed_or_superseded, transitional_rule, known_exceptions, review_state, canonical_url
) values
  (
    'prov-ipc-1860-s420',
    'ipc-1860',
    'Indian Penal Code, 1860',
    'Section 420',
    'criminal',
    'India',
    '1860-2024',
    'sha256-ipc-420-v1',
    'Cheating and dishonestly inducing delivery of property for offences committed before 1 July 2024.',
    'Section 420. Cheating and dishonestly inducing delivery of property.—Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person... shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.',
    '1862-01-01',
    '2024-06-30',
    true,
    'Substantive offences committed prior to 1 July 2024 continue to be governed by IPC Section 420 under Section 358 of the Bharatiya Nyaya Sanhita, 2023 and Section 6 of the General Clauses Act, 1897.',
    '["Pure civil breach of contract without fraudulent intention at the time of inducement does not constitute cheating."]'::jsonb,
    'qualified_legal_reviewed',
    'https://www.indiacode.nic.in/bitstream/123456789/15289/1/ipc_act.pdf'
  ),
  (
    'prov-bns-2023-s318',
    'bns-2023',
    'Bharatiya Nyaya Sanhita, 2023',
    'Section 318(4)',
    'criminal',
    'India',
    '2024-current',
    'sha256-bns-318-v1',
    'Cheating and dishonestly inducing delivery of property for offences committed on or after 1 July 2024.',
    'Section 318(4). Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person... shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.',
    '2024-07-01',
    null,
    false,
    'Applies to substantive cheating offences committed on or after 1 July 2024 (replacing IPC Section 420).',
    '["Pre-1 July 2024 substantive conduct remains governed by IPC Section 420 under BNS Section 358 savings."]'::jsonb,
    'qualified_legal_reviewed',
    'https://www.indiacode.nic.in/'
  ),
  (
    'prov-crpc-1973-s154',
    'crpc-1973',
    'Code of Criminal Procedure, 1973',
    'Section 154',
    'criminal',
    'India',
    '1974-2024',
    'sha256-crpc-154-v1',
    'Information in cognizable cases (FIR registration) for proceedings pending before 1 July 2024.',
    'Section 154. Information in cognizable cases.—Every information relating to the commission of a cognizable offence, if given orally to an officer in charge of a police station, shall be reduced to writing.',
    '1974-04-01',
    '2024-06-30',
    true,
    'Under BNSS Section 531(2)(a), any investigation, inquiry, trial, or appeal pending immediately before 1 July 2024 continues under CrPC, 1973. Fresh FIRs registered on or after 1 July 2024 follow BNSS Section 173.',
    '["Fresh FIR registration on or after 1 July 2024 follows BNSS Section 173 even if the underlying offence occurred before 1 July 2024."]'::jsonb,
    'qualified_legal_reviewed',
    'https://www.indiacode.nic.in/bitstream/123456789/15272/1/crpc_1973.pdf'
  ),
  (
    'prov-bnss-2023-s173',
    'bnss-2023',
    'Bharatiya Nagarik Suraksha Sanhita, 2023',
    'Section 173 & Section 531',
    'criminal',
    'India',
    '2024-current',
    'sha256-bnss-173-v1',
    'Information in cognizable cases (including Zero FIR and electronic communication) and transitional savings under Section 531.',
    'Section 173(1). Every information relating to the commission of a cognizable offence, irrespective of the area where the offence is committed, may be given orally or by electronic communication to an officer in charge of a police station.',
    '2024-07-01',
    null,
    false,
    'Governs fresh FIR registration on or after 1 July 2024; Section 531(2)(a) saves pending pre-1 July 2024 investigations/trials under CrPC, 1973.',
    '["Electronic FIR information under Section 173(1)(ii) requires signature by the person giving it within three days to be taken on record."]'::jsonb,
    'qualified_legal_reviewed',
    'https://www.ncrb.mha.gov.in/uploads/SankalanPortal/DownloadPDF/BNSS2023.pdf'
  ),
  (
    'prov-cpa-2019-s35-s69',
    'cpa-2019',
    'Consumer Protection Act, 2019',
    'Sections 2(7), 2(10), 2(11), 35 & 69',
    'consumer',
    'India',
    '2020-current',
    'sha256-cpa-2019-s35-v1',
    'District Commission complaint for defective goods, deficiency in service, and two-year limitation.',
    'A complaint in relation to any goods sold or delivered or any service provided may be filed with a District Commission within two years from the date on which the cause of action has arisen.',
    '2020-07-20',
    null,
    false,
    'Replaced the Consumer Protection Act, 1986 with effect from 20 July 2020.',
    '["Excludes goods or services obtained for commercial purpose unless exclusively for earning livelihood by means of self-employment."]'::jsonb,
    'qualified_legal_reviewed',
    'https://www.indiacode.nic.in/bitstream/123456789/15256/1/eng201935.pdf'
  ),
  (
    'prov-rbi-failed-tx-2019',
    'rbi-tat-2019',
    'RBI Harmonisation of Turn Around Time (TAT) and Customer Compensation for Failed Transactions',
    'Circular DPSS.CO.PD No.629/02.01.014/2019-20',
    'banking',
    'India',
    '2019-current',
    'sha256-rbi-tat-2019-v1',
    'Auto-reversal timelines (T+1 / T+5) and ₹100/day statutory compensation for delayed reversal of failed UPI, IMPS, and card transactions.',
    'Where a transaction fails and the customer account is debited without credit to the beneficiary, the bank/issuer must auto-reverse within the prescribed TAT (T+1 day for UPI/IMPS), failing which financial compensation of Rs. 100 per day of delay beyond TAT is payable.',
    '2019-10-15',
    null,
    false,
    'Applies to authorised payment systems where account is debited but beneficiary/merchant is not credited due to technical failure.',
    '["Does not apply to completed transfers to an unintended beneficiary or induced fraud transfers where money reached the recipient account."]'::jsonb,
    'qualified_legal_reviewed',
    'https://www.rbi.org.in/'
  )
on conflict (provision_id) do nothing;

insert into public.nyay_legal_relations (
  id, from_provision_id, to_provision_id, relation_type, cutoff_date, procedural_rule
) values
  (
    'rel-ipc420-to-bns318',
    'prov-ipc-1860-s420',
    'prov-bns-2023-s318',
    'superseded_by',
    '2024-07-01',
    'Substantive offence date < 2024-07-01 uses IPC Section 420; offence date >= 2024-07-01 uses BNS Section 318(4).'
  ),
  (
    'rel-crpc154-to-bnss173',
    'prov-crpc-1973-s154',
    'prov-bnss-2023-s173',
    'transitional_saving',
    '2024-07-01',
    'Under BNSS Section 531(2)(a), investigations/trials pending before 2024-07-01 continue under CrPC 1973; fresh FIRs registered on or after 2024-07-01 follow BNSS Section 173.'
  )
on conflict (id) do nothing;
