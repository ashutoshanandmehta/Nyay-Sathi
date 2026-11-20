-- Read-only bootstrap integrity check. Apply only to Nyay Saathi.
select
  (select count(*) from public.nyay_legal_sources) as sources,
  (select count(*) from public.nyay_legal_documents) as documents,
  count(*) as passages,
  count(*) filter (where review_state = 'approved') as approved,
  count(*) filter (where review_state = 'pending') as pending,
  count(*) filter (where embedding_model = 'text-embedding-3-small'
    and embedding_version = 'openai:text-embedding-3-small:dimensions=384:v1'
    and embedding_dimensions = 384 and cardinality(embedding_f32) = 384) as compatible_vectors,
  has_function_privilege('service_role',
    'public.nyay_legal_hybrid_search(text,double precision[],text,date,date,integer)', 'EXECUTE') as service_search,
  has_function_privilege('authenticated',
    'public.nyay_legal_hybrid_search(text,double precision[],text,date,date,integer)', 'EXECUTE') as authenticated_search
from public.nyay_legal_passages;

-- Compare a stored reference vector to itself. This checks seed and SQL wiring.
-- It does not validate a hosted query embedder.
select r.passage_id, r.semantic_rank, r.cosine_score
from public.nyay_legal_passages p
cross join lateral public.nyay_legal_hybrid_search(
  'failed UPI reversal',p.embedding_f32,null,null,date '2026-11-20',12
) r
where p.passage_id = 'rbi-2019-failed-tx-tat-rules'
  and r.passage_id = p.passage_id;
