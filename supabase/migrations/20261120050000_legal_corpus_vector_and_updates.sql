-- Versioned Public Legal Corpus, Multilingual Vector/Lexical Retrieval,
-- and Bounded Continuous Update Pipeline.
-- Strictly isolated from private case tables (nyay_cases, nyay_case_documents, nyay_messages).

-- 1. Enable pgvector when available (hosted Supabase); degrade gracefully in embedded PGlite.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'vector') then
    execute 'create extension if not exists vector';
  end if;
end $$;

-- 2. Trusted Official Source Registry & Discovered Candidates (never auto-promoted from private data).
create table if not exists public.nyay_legal_sources (
  source_id text primary key check (source_id ~ '^[a-z0-9][a-z0-9._-]{1,99}$'),
  title text not null check (char_length(title) between 2 and 300),
  authority text not null check (char_length(authority) between 2 and 240),
  canonical_url text not null check (canonical_url ~ '^https://[^@]+$'),
  domain text not null check (domain in ('consumer', 'financial_fraud', 'banking_payments', 'criminal', 'legal_aid', 'general')),
  region text not null default 'India' check (char_length(region) between 2 and 80),
  source_type text not null check (source_type in (
    'primary_legislation',
    'rules',
    'regulations',
    'commencement_notification',
    'regulator_circular',
    'master_direction',
    'official_procedural_guidance',
    'official_referral_guidance',
    'judgment',
    'corrigendum',
    'amending_rules'
  )),
  trust_tier text not null default 'trusted_registry'
    check (trust_tier in ('trusted_registry', 'agent_discovered_candidate', 'suspended')),
  ingest_enabled boolean not null default true,
  refresh_interval_hours integer not null default 168 check (refresh_interval_hours >= 1),
  latest_content_hash text,
  latest_version text,
  last_checked_at timestamptz,
  last_success_at timestamptz,
  last_failure_at timestamptz,
  failure_count integer not null default 0 check (failure_count >= 0),
  last_error text not null default '',
  retry_after timestamptz,
  known_limitations text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. Versioned Original Source Document Snapshots.
create table if not exists public.nyay_legal_documents (
  document_id text primary key check (document_id ~ '^[A-Za-z0-9_.-]{2,100}$'),
  source_id text not null references public.nyay_legal_sources(source_id) on delete restrict,
  version text not null check (char_length(version) between 1 and 80),
  title text not null check (char_length(title) between 2 and 300),
  official_url text not null check (official_url ~ '^https://[^@]+$'),
  authority text not null check (char_length(authority) between 2 and 240),
  region text not null default 'India',
  source_language text not null default 'en',
  publication_date date,
  effective_from date,
  effective_until date,
  date_independent boolean not null default false,
  content_hash text not null check (char_length(content_hash) >= 16),
  raw_storage_path text not null default '',
  review_state text not null default 'pending'
    check (review_state in ('approved', 'pending', 'retired')),
  is_active boolean not null default false,
  supersedes_document_id text references public.nyay_legal_documents(document_id),
  superseded_by_document_id text references public.nyay_legal_documents(document_id),
  acquired_at timestamptz not null default now(),
  reviewed_by text,
  reviewed_at timestamptz,
  limitations text[] not null default '{}'::text[],
  cache_epoch integer not null default 1 check (cache_epoch > 0),
  unique (source_id, version)
);

-- 4. Extracted Original Passages + Provenance + Multilingual Embeddings.
create table if not exists public.nyay_legal_passages (
  passage_id text primary key
    check (passage_id ~ '^[A-Za-z0-9_.-]{1,100}$' and passage_id not like 'segment%'),
  document_id text not null references public.nyay_legal_documents(document_id) on delete cascade,
  source_id text not null references public.nyay_legal_sources(source_id) on delete restrict,
  version text not null check (char_length(version) between 1 and 80),
  title text not null check (char_length(title) between 2 and 300),
  locator text not null check (char_length(locator) between 1 and 300),
  text text not null check (char_length(text) between 20 and 3200),
  official_url text not null check (official_url ~ '^https://[^@]+$'),
  authority text not null check (char_length(authority) between 2 and 240),
  region text not null default 'India',
  domain text not null default 'consumer',
  source_language text not null default 'en',
  valid_from date,
  valid_until date,
  date_independent boolean not null default false,
  acquired_at timestamptz not null default now(),
  review_state text not null default 'pending'
    check (review_state in ('approved', 'pending', 'retired')),
  is_active boolean not null default false,
  limitations text[] not null default '{}'::text[],
  related_passage_ids text[] not null default '{}'::text[],
  keywords text[] not null default '{}'::text[],
  content_hash text not null check (char_length(content_hash) >= 16),
  search_tsv tsvector generated always as (
    to_tsvector(
      'english',
      coalesce(title, '') || ' ' || coalesce(locator, '') || ' ' || coalesce(text, '')
    ) ||
    to_tsvector(
      'simple',
      coalesce(title, '') || ' ' || coalesce(locator, '') || ' ' || coalesce(text, '')
    )
  ) stored,
  embedding_f32 double precision[],
  embedding_model text not null default 'text-embedding-3-small',
  embedding_version text not null default 'openai:text-embedding-3-small:dimensions=384:v1',
  embedding_dimensions integer not null default 384 check (embedding_dimensions > 0),
  cache_epoch integer not null default 1 check (cache_epoch > 0),
  created_at timestamptz not null default now()
);

-- Attach native pgvector column + HNSW cosine index + sync trigger when pgvector extension is installed.
do $$
declare vector_schema text;
begin
  select n.nspname into vector_schema from pg_extension e join pg_namespace n on n.oid=e.extnamespace
  where e.extname='vector';
  if vector_schema is not null then
    execute format('alter table public.nyay_legal_passages add column if not exists embedding %I.vector(384)', vector_schema);
    execute format('create index if not exists nyay_legal_passages_embedding_hnsw on public.nyay_legal_passages using hnsw (embedding %I.vector_cosine_ops)', vector_schema);
    execute format($fn$
      create or replace function public.nyay_sync_passage_pgvector()
      returns trigger
      language plpgsql
      set search_path = ''
      as $trig$
      begin
        if new.embedding_f32 is not null and array_length(new.embedding_f32, 1) = 384 then
          new.embedding := (new.embedding_f32::real[])::%I.vector(384);
        else
          new.embedding := null;
        end if;
        return new;
      end $trig$;
    $fn$, vector_schema);
    execute 'drop trigger if exists nyay_legal_passages_sync_vec on public.nyay_legal_passages';
    execute 'create trigger nyay_legal_passages_sync_vec before insert or update of embedding_f32 on public.nyay_legal_passages for each row execute function public.nyay_sync_passage_pgvector()';
  end if;
end $$;

create index if not exists nyay_legal_passages_tsv_gin
  on public.nyay_legal_passages using gin(search_tsv);
create index if not exists nyay_legal_passages_applicability
  on public.nyay_legal_passages(region, review_state, is_active, valid_from, valid_until);
create index if not exists nyay_legal_passages_document
  on public.nyay_legal_passages(document_id, version);

-- 5. Passage-Level Definitions, Exceptions, Amendments & Predecessor/Successor Relations.
create table if not exists public.nyay_legal_passage_relations (
  id text primary key,
  from_passage_id text not null references public.nyay_legal_passages(passage_id) on delete cascade,
  to_passage_id text not null references public.nyay_legal_passages(passage_id) on delete cascade,
  relation_type text not null check (relation_type in (
    'requires_definition',
    'requires_exception',
    'superseded_by',
    'amended_by',
    'transitional_saving',
    'state_amendment',
    'cross_reference'
  )),
  cutoff_date date,
  notes text not null default ''
);

-- 6. Bounded Resumable Update Pipeline Jobs (never accepts private case data or model self-certification).
create table if not exists public.nyay_legal_update_jobs (
  job_id uuid primary key default gen_random_uuid(),
  source_id text not null references public.nyay_legal_sources(source_id) on delete cascade,
  trigger_type text not null check (trigger_type in ('scheduled', 'discovered_candidate', 'manual')),
  stage text not null default 'queued' check (stage in (
    'queued',
    'fetching',
    'diffing',
    'validating',
    'pending_review',
    'embedding',
    'ready_to_activate',
    'activated',
    'no_change',
    'rejected',
    'rolled_back',
    'failed'
  )),
  candidate_url text not null check (candidate_url ~ '^https://[^@]+$'),
  candidate_hash text,
  previous_version text,
  candidate_version text,
  candidate_document_id text references public.nyay_legal_documents(document_id),
  diff_summary jsonb not null default '{}'::jsonb,
  changed_passage_ids text[] not null default '{}'::text[],
  material_change boolean not null default true,
  auto_promotable boolean not null default false,
  review_state text not null default 'pending'
    check (review_state in ('pending', 'approved', 'rejected', 'not_required')),
  reviewer_id text,
  review_notes text not null default '',
  error_detail text not null default '',
  attempts integer not null default 0 check (attempts >= 0),
  lease_token uuid,
  lease_until timestamptz,
  due_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists nyay_legal_update_jobs_due
  on public.nyay_legal_update_jobs(stage, due_at);

-- 7. Immutable Editorial & Activation Audit Log + Epoch-Scoped Retrieval Cache.
create table if not exists public.nyay_legal_audit_log (
  id bigint generated always as identity primary key,
  source_id text not null,
  document_id text,
  job_id uuid,
  action text not null check (action in (
    'check_unchanged',
    'check_failed',
    'candidate_staged',
    'validation_failed',
    'editorial_approved',
    'editorial_rejected',
    'auto_promoted_non_semantic',
    'version_activated',
    'cache_invalidated',
    'version_rolled_back'
  )),
  actor text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.nyay_legal_retrieval_cache (
  cache_key text primary key,
  cache_epoch integer not null check (cache_epoch > 0),
  region text,
  incident_date date,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.nyay_legal_corpus_state (
  singleton boolean primary key default true check (singleton = true),
  cache_epoch integer not null default 1 check (cache_epoch > 0),
  active_corpus_version text not null default 'v1',
  embedding_model text not null default 'text-embedding-3-small',
  embedding_version text not null default 'openai:text-embedding-3-small:dimensions=384:v1',
  embedding_dimensions integer not null default 384,
  updated_at timestamptz not null default now()
);
insert into public.nyay_legal_corpus_state (singleton) values (true) on conflict do nothing;

-- 8. Row-Level Security: Public approved corpus is read-only for clients; update internals are service-only.
do $$
declare t text;
begin
  foreach t in array array[
    'nyay_legal_sources',
    'nyay_legal_documents',
    'nyay_legal_passages',
    'nyay_legal_passage_relations',
    'nyay_legal_corpus_state'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from public, anon, authenticated', t);
    execute format('grant select on table public.%I to authenticated', t);
    execute format('grant all on table public.%I to service_role', t);
  end loop;

  foreach t in array array[
    'nyay_legal_update_jobs',
    'nyay_legal_audit_log',
    'nyay_legal_retrieval_cache'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on table public.%I from public, anon, authenticated', t);
    execute format('grant all on table public.%I to service_role', t);
  end loop;
end $$;

create policy legal_sources_select_auth on public.nyay_legal_sources
  for select to authenticated using (trust_tier = 'trusted_registry');
create policy legal_docs_select_auth on public.nyay_legal_documents
  for select to authenticated using (review_state = 'approved');
create policy legal_passages_select_auth on public.nyay_legal_passages
  for select to authenticated using (review_state = 'approved');
create policy legal_passage_rels_select_auth on public.nyay_legal_passage_relations
  for select to authenticated using (true);
create policy legal_corpus_state_select_auth on public.nyay_legal_corpus_state
  for select to authenticated using (true);

-- 9. Cosine Similarity Helper (works both in PGlite via double precision[] and hosted pgvector).
create or replace function public.nyay_array_cosine_similarity(a double precision[], b double precision[])
returns double precision
language sql
immutable
strict
as $$
  select case
    when array_length(a, 1) is null or array_length(b, 1) is null or array_length(a, 1) <> array_length(b, 1) then 0.0
    else (
      select coalesce(sum(x * y), 0.0) /
        nullif(sqrt(coalesce(sum(x * x), 0.0)) * sqrt(coalesce(sum(y * y), 0.0)), 0.0)
      from unnest(a, b) as t(x, y)
    )
  end
$$;

-- 10. Hybrid Semantic + Lexical Search RPC with Independent Branches, Region & Date Applicability.
create or replace function public.nyay_legal_hybrid_search(
  p_query text,
  p_query_embedding double precision[] default null,
  p_region text default null,
  p_incident_date date default null,
  p_as_of_date date default current_date,
  p_limit integer default 6
)
returns table (
  passage_id text,
  document_id text,
  title text,
  text text,
  locator text,
  official_url text,
  authority text,
  region text,
  valid_from date,
  valid_until date,
  date_independent boolean,
  version text,
  acquired_at timestamptz,
  review_state text,
  limitations text[],
  related_passage_ids text[],
  lexical_rank integer,
  semantic_rank integer,
  cosine_score double precision,
  rrf_score double precision
)
language sql
stable
security invoker
set search_path = ''
as $$
  with effective_target as (
    select coalesce(p_incident_date, p_as_of_date) as target_date
  ),
  query_tokens as (
    select string_agg(distinct tok, ' | ') as or_expr
    from (
      select lower(regexp_replace(w, '[^a-zA-Z0-9\u0900-\u097F]', '', 'g')) as tok
      from regexp_split_to_table(coalesce(p_query, ''), '\s+') as w
    ) t
    where length(tok) >= 2
      and tok not in (
        'am', 'an', 'as', 'at', 'be', 'by', 'did', 'do', 'does', 'for', 'from',
        'has', 'have', 'he', 'her', 'him', 'his', 'how', 'if', 'in', 'into', 'is',
        'it', 'its', 'me', 'my', 'no', 'not', 'of', 'on', 'or', 'our', 'she',
        'so', 'that', 'the', 'their', 'them', 'this', 'to', 'up', 'us', 'was',
        'we', 'were', 'what', 'when', 'where', 'which', 'who', 'why', 'will',
        'with', 'you', 'your'
      )
  ),
  parsed_tsq as (
    select case
      when (select or_expr from query_tokens) is not null then
        to_tsquery('english', (select or_expr from query_tokens)) ||
        to_tsquery('simple', (select or_expr from query_tokens))
      else null::tsquery
    end as tsq
  ),
  eligible as (
    select p.*
    from public.nyay_legal_passages p, effective_target et
    where p.review_state = 'approved'
      and p.embedding_model = 'text-embedding-3-small'
      and p.embedding_version = 'openai:text-embedding-3-small:dimensions=384:v1'
      and p.embedding_dimensions = 384
      and cardinality(p.embedding_f32) = 384
      and (p.region = 'India' or (p_region is not null and p.region = p_region))
      and (
        p.date_independent = true
        or (
          p.valid_from is not null
          and p.valid_from <= et.target_date
          and (p.valid_until is null or et.target_date < p.valid_until)
        )
      )
      -- Prefer active versions on current-law queries, while permitting approved scheduled versions whose valid_from has arrived.
      and (
        p.is_active = true
        or p_incident_date is not null
        or (p.valid_from is not null and p.valid_from <= et.target_date and (p.valid_until is null or et.target_date < p.valid_until))
      )
  ),
  lex as (
    select
      e.passage_id,
      row_number() over (
        order by ts_rank_cd(e.search_tsv, pt.tsq) desc, e.passage_id
      )::integer as rnk
    from eligible e, parsed_tsq pt
    where pt.tsq is not null
      and e.search_tsv @@ pt.tsq
    limit 24
  ),
  sem as (
    select
      e.passage_id,
      public.nyay_array_cosine_similarity(e.embedding_f32, p_query_embedding) as sim,
      row_number() over (
        order by public.nyay_array_cosine_similarity(e.embedding_f32, p_query_embedding) desc, e.passage_id
      )::integer as rnk
    from eligible e
    where p_query_embedding is not null
      and e.embedding_f32 is not null
    limit 24
  ),
  fused as (
    select
      coalesce(l.passage_id, s.passage_id) as passage_id,
      l.rnk as lexical_rank,
      s.rnk as semantic_rank,
      (case when l.rnk is not null then 2.0 / (60.0 + l.rnk) else 0.0 end) +
      (case when s.rnk is not null then 1.0 / (60.0 + s.rnk) else 0.0 end) as rrf_score
    from lex l
    full outer join sem s on l.passage_id = s.passage_id
  )
  select
    e.passage_id,
    e.document_id,
    e.title,
    e.text,
    e.locator,
    e.official_url,
    e.authority,
    e.region,
    e.valid_from,
    e.valid_until,
    e.date_independent,
    e.version,
    e.acquired_at,
    e.review_state,
    e.limitations,
    e.related_passage_ids,
    f.lexical_rank,
    f.semantic_rank,
    case
      when p_query_embedding is not null and e.embedding_f32 is not null
        then public.nyay_array_cosine_similarity(e.embedding_f32, p_query_embedding)
      else 0.0
    end as cosine_score,
    f.rrf_score
  from fused f
  join eligible e on e.passage_id = f.passage_id
  order by f.rrf_score desc, cosine_score desc, e.passage_id
  limit greatest(1, least(coalesce(p_limit, 6), 24));
$$;

-- 11. Atomic Candidate Activation, Cache Invalidation, and Rollback RPCs (service_role only).
create or replace function public.nyay_legal_activate_candidate(
  p_job_id uuid,
  p_reviewer_id text,
  p_review_notes text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.nyay_legal_update_jobs;
  v_doc public.nyay_legal_documents;
  v_new_epoch integer;
  v_prev_doc_id text;
  v_is_future boolean;
begin
  select * into v_job from public.nyay_legal_update_jobs where job_id = p_job_id for update;
  if not found then
    raise exception 'Update job not found' using errcode = 'P0002';
  end if;
  if v_job.candidate_document_id is null then
    raise exception 'Update job has no staged candidate document' using errcode = '22023';
  end if;
  if v_job.material_change and (p_reviewer_id is null or length(trim(p_reviewer_id)) < 2) then
    raise exception 'Editorial reviewer identity required for material legal change' using errcode = '42501';
  end if;
  if lower(trim(coalesce(p_reviewer_id, ''))) ~ '^(model:|llm:|ai:|agent:|gpt|claude|gemini)' then
    raise exception 'Model cannot certify its own legal interpretation' using errcode = '42501';
  end if;

  select * into v_doc from public.nyay_legal_documents where document_id = v_job.candidate_document_id for update;
  v_is_future := (v_doc.effective_from is not null and v_doc.effective_from > current_date);

  select document_id into v_prev_doc_id
  from public.nyay_legal_documents
  where source_id = v_doc.source_id and is_active = true and document_id <> v_doc.document_id
  limit 1;

  update public.nyay_legal_corpus_state
  set cache_epoch = cache_epoch + 1,
      updated_at = now()
  where singleton = true
  returning cache_epoch into v_new_epoch;

  if v_is_future then
    -- Future-effective: approve & stage without deactivating current law before effective_from.
    if v_prev_doc_id is not null then
      update public.nyay_legal_documents
      set effective_until = coalesce(effective_until, v_doc.effective_from),
          cache_epoch = v_new_epoch
      where document_id = v_prev_doc_id;

      update public.nyay_legal_passages
      set valid_until = coalesce(valid_until, v_doc.effective_from),
          cache_epoch = v_new_epoch
      where document_id = v_prev_doc_id;
    end if;

    update public.nyay_legal_documents
    set review_state = 'approved',
        is_active = false,
        supersedes_document_id = coalesce(supersedes_document_id, v_prev_doc_id),
        reviewed_by = p_reviewer_id,
        reviewed_at = now(),
        cache_epoch = v_new_epoch
    where document_id = v_doc.document_id;

    update public.nyay_legal_passages
    set review_state = 'approved',
        is_active = false,
        cache_epoch = v_new_epoch
    where document_id = v_doc.document_id;
  else
    if v_prev_doc_id is not null then
      -- Preserve prior version for historical incident_date queries; mark superseded pointer.
      update public.nyay_legal_documents
      set is_active = false,
          superseded_by_document_id = v_doc.document_id,
          effective_until = coalesce(effective_until, v_doc.effective_from),
          cache_epoch = v_new_epoch
      where document_id = v_prev_doc_id;

      update public.nyay_legal_passages
      set is_active = false,
          valid_until = coalesce(valid_until, v_doc.effective_from),
          cache_epoch = v_new_epoch
      where document_id = v_prev_doc_id;
    end if;

    update public.nyay_legal_documents
    set review_state = 'approved',
        is_active = true,
        supersedes_document_id = coalesce(supersedes_document_id, v_prev_doc_id),
        reviewed_by = p_reviewer_id,
        reviewed_at = now(),
        cache_epoch = v_new_epoch
    where document_id = v_doc.document_id;

    update public.nyay_legal_passages
    set review_state = 'approved',
        is_active = true,
        cache_epoch = v_new_epoch
    where document_id = v_doc.document_id;

    update public.nyay_legal_sources
    set latest_content_hash = v_doc.content_hash,
        latest_version = v_doc.version,
        last_success_at = now(),
        failure_count = 0,
        last_error = '',
        updated_at = now()
    where source_id = v_doc.source_id;
  end if;

  delete from public.nyay_legal_retrieval_cache where cache_epoch < v_new_epoch;

  update public.nyay_legal_update_jobs
  set stage = 'activated',
      review_state = case when v_job.material_change then 'approved' else 'not_required' end,
      reviewer_id = p_reviewer_id,
      review_notes = coalesce(p_review_notes, ''),
      updated_at = now()
  where job_id = p_job_id;

  insert into public.nyay_legal_audit_log(source_id, document_id, job_id, action, actor, details)
  values (
    v_doc.source_id,
    v_doc.document_id,
    p_job_id,
    'version_activated',
    p_reviewer_id,
    jsonb_build_object(
      'previous_document_id', v_prev_doc_id,
      'cache_epoch', v_new_epoch,
      'future_effective', v_is_future,
      'review_notes', coalesce(p_review_notes, '')
    )
  );

  return jsonb_build_object(
    'activated_document_id', v_doc.document_id,
    'previous_document_id', v_prev_doc_id,
    'future_effective', v_is_future,
    'cache_epoch', v_new_epoch
  );
end $$;

create or replace function public.nyay_legal_rollback_version(
  p_source_id text,
  p_target_document_id text,
  p_actor text,
  p_reason text default ''
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_target public.nyay_legal_documents;
  v_current_id text;
  v_new_epoch integer;
begin
  select * into v_target
  from public.nyay_legal_documents
  where document_id = p_target_document_id and source_id = p_source_id
  for update;

  if not found then
    raise exception 'Rollback target document not found' using errcode = 'P0002';
  end if;

  select document_id into v_current_id
  from public.nyay_legal_documents
  where source_id = p_source_id and is_active = true and document_id <> p_target_document_id
  limit 1;

  update public.nyay_legal_corpus_state
  set cache_epoch = cache_epoch + 1,
      updated_at = now()
  where singleton = true
  returning cache_epoch into v_new_epoch;

  if v_current_id is not null then
    update public.nyay_legal_documents
    set is_active = false,
        review_state = 'retired',
        cache_epoch = v_new_epoch
    where document_id = v_current_id;

    update public.nyay_legal_passages
    set is_active = false,
        review_state = 'retired',
        cache_epoch = v_new_epoch
    where document_id = v_current_id;
  end if;

  update public.nyay_legal_documents
  set is_active = true,
      review_state = 'approved',
      effective_until = null,
      superseded_by_document_id = null,
      cache_epoch = v_new_epoch
  where document_id = p_target_document_id;

  update public.nyay_legal_passages
  set is_active = true,
      review_state = 'approved',
      valid_until = null,
      cache_epoch = v_new_epoch
  where document_id = p_target_document_id;

  update public.nyay_legal_sources
  set latest_version = v_target.version,
      latest_content_hash = v_target.content_hash,
      updated_at = now()
  where source_id = p_source_id;

  delete from public.nyay_legal_retrieval_cache where cache_epoch < v_new_epoch;

  insert into public.nyay_legal_audit_log(source_id, document_id, action, actor, details)
  values (
    p_source_id,
    p_target_document_id,
    'version_rolled_back',
    p_actor,
    jsonb_build_object(
      'retired_document_id', v_current_id,
      'cache_epoch', v_new_epoch,
      'reason', coalesce(p_reason, '')
    )
  );

  return jsonb_build_object(
    'restored_document_id', p_target_document_id,
    'retired_document_id', v_current_id,
    'cache_epoch', v_new_epoch
  );
end $$;

revoke all on function public.nyay_legal_activate_candidate(uuid, text, text) from public, anon, authenticated;
grant execute on function public.nyay_legal_activate_candidate(uuid, text, text) to service_role;

revoke all on function public.nyay_legal_rollback_version(text, text, text, text) from public, anon, authenticated;
grant execute on function public.nyay_legal_rollback_version(text, text, text, text) to service_role;

revoke all on function public.nyay_legal_hybrid_search(text, double precision[], text, date, date, integer) from public, anon, authenticated;
grant execute on function public.nyay_legal_hybrid_search(text, double precision[], text, date, date, integer) to service_role;
