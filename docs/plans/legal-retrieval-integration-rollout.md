# Legal retrieval integration rollout

Target project `daojcrxjjkqoirqbvhjn`. This is a prepared rollout. The migrations, corpus seed, and worker passed through the local PGlite journey. The live project and protected Vercel demo were untouched.

The worker calls the Supabase hybrid RPC using versioned OpenAI 384-dimensional vectors. It permits as-of-date retrieval for clearly general current-law questions, uses the stored case date for confirmed incidents, and withholds time-bound evidence when an incident date needs confirmation. It never fills the incident date field from the evaluation date. Citation metadata retains the provision, official URL, document version, and acquisition date. Automated approval does not imply independent advocate certification of the corpus.

**Qualification update:** Two dedicated Tokyo E5 probes failed before inference. The probe is retired and hosted rollout remains gated. See the [measurements and managed alternative](hosted-e5-qualification-2026-11-20.md).

## Query embedding gate

**Owner-approved update, 20 November 2026:** the failed hosted E5 approach is replaced by `text-embedding-3-small` with `dimensions=384`. The entire 50-passage corpus was re-embedded in the new vector space; E5 and OpenAI vectors are never mixed. The version is `openai:text-embedding-3-small:dimensions=384:v1`. Admission remains paused until the multilingual hybrid gate and hosted secret/migration checks pass. Query text is sent to OpenAI and may contain personal data; default API abuse-monitoring retention can be up to 30 days unless the project is approved and configured for Zero Data Retention.

The prior E5 vectors remain reference evidence only. The active corpus manifest, SQL seed, runtime adapter, and query fixtures all pin the same OpenAI model and dimensions. Changing either requires a complete re-embedding and a new qualification report.

The application and corpus stay on Supabase. Query embedding is one bounded HTTPS call from the Edge worker to OpenAI; no model artifact runs inside the Edge isolate. The request includes a fixed canary and the user query. Canary cosine below `0.99999`, a wrong model name, malformed indexes, non-finite values, or wrong dimensions fails the persisted retrieval step rather than mixing vector spaces.

The worker requests `{input:[canary,userQuery],model:"text-embedding-3-small",dimensions:384,encoding_format:"float"}` with bearer authentication, a three-second timeout, redirects disabled, a bounded response body, and strict validation. The worker sends query text, which can contain personal information, and does not send the evidence registry or attachment files. Default OpenAI abuse-monitoring retention may be up to 30 days unless approved and configured for Zero Data Retention. Missing or invalid configuration disables new admission. Failed or drifted responses exhaust bounded retries and report unavailable. The reviewed legal path does not use a keyword-only fallback.

The generation defaults remain **GPT-6.2 Sol Medium** with the existing SQL reservation and reconciliation. No embedding spend is charged to that ledger. The local re-embedding used 22,369 input tokens across four requests; the first writer attempt repeated those calls once after a Python 3.9 compatibility failure, before checkpoints were added. Query qualification made two small 15-query calls; subsequent rebuilds and evaluations reused content-hashed checkpoints with zero provider submissions. A verified provider/project hard cap or a budget-ledger extension is still required before admission can open. If the model or preprocessing changes, re-embed all corpus rows, rerun the complete hybrid evaluation, and switch query and corpus versions together.

## Hosted sequence

1. Reconcile the Supabase migration history with the foundation and budget receipts. Use Supabase CLI v3. Check the project ID in every command and review backups and pending migrations before changing the project.
2. Apply the database prerequisites and the legal migration. On an empty legal source registry, run the guarded bootstrap seed once. It aborts on a nonempty source registry to preserve editorial work.
3. Verify the seed and access boundary. Expect 29 sources, 29 documents, 50 passages, 49 approved, one pending, 50 compatible vectors, service access true, and authenticated search RPC access false. The bounded prototype query uses exact array cosine with tsvector and RRF. It does not depend on the HNSW index for correctness. Confirm extension, trigger, plan, and latency on hosted Postgres.
4. Keep `NYAY_PAUSE_TURN_ADMISSION=true` while configuring and deploying the Edge function. Supply a project-scoped `OPENAI_EMBEDDING_API_KEY` through the target project's Edge Function secret manager; `OPENAI_API_KEY` is supported only as a compatibility fallback. Keep embedding and generation keys distinct where possible. Verify a provider/project hard spend cap before opening admission. Use the [resumable backend runbook](backend-resumable-local-handoff.md) for Cron, webhook, and recovery setup.
5. Before opening the pilot, verify hosted admission, budget settlement, semantic retrieval and citations on synthetic non-sensitive prompts. Check reconnect, historical scope, unsupported coverage, embedder outage, and cross-owner isolation. Obtain qualified review for the intended public legal scope. Roll back by pausing admission and restoring the prior function after draining. Preserve the corpus and event history. Corpus refresh and editorial activation remain a separate workflow.

```sh
npx supabase migration list --remote=daojcrxjjkqoirqbvhjn
npx supabase db push --dry-run --skip-vault --remote=daojcrxjjkqoirqbvhjn
# After review and release authorization
npx supabase db push --skip-vault --remote=daojcrxjjkqoirqbvhjn
npx supabase db query --remote=daojcrxjjkqoirqbvhjn --file data/legal_corpus/v1/seed_legal_corpus.sql
npx supabase db query --read-only --remote=daojcrxjjkqoirqbvhjn --file supabase/operations/legal-corpus-verify.sql
npx supabase functions deploy nyay-api --remote=daojcrxjjkqoirqbvhjn
```

`cd frontend && npm test -- src/openai-legal-retrieval-qualification.test.ts src/legal-agent-journey.test.ts --maxWorkers=1` runs all 15 inherited retrieval cases plus a null-incident general-current-law case and the reviewed journey using recorded vectors generated by the exact API configuration. It does not measure live model answer quality, hosted latency, or Android device behavior.
