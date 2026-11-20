# Android database foundation deployment

Date: 19 November 2026.

Project: `daojcrxjjkqoirqbvhjn`, organization **Nyay Sathi** (`eatddnxpdlcocibvfohd`), region `ap-northeast-1`.

The connector returned `Unknown tool` for project and organization reads after reconnection. The existing authenticated Brave dashboard session had Owner access to the specified project, so the dashboard SQL Editor was used as a fallback. The public schema's table editor showed no existing tables before applying the migration.

Applied the definitions in `supabase/migrations/20261119091306_android_backend_foundation.sql` inside an explicit transaction, followed by the verification query in `supabase/tests/foundation-verification.sql`. The dashboard's “Run and enable RLS” option was selected in addition to the migration's own RLS statements. The query completed and displayed these seven rows:

| Table | RLS enabled | Unauthenticated SELECT | Authenticated INSERT |
|---|---|---|---|
| nyay_case_memory | true | false | false |
| nyay_cases | true | false | true |
| nyay_conversations | true | false | true |
| nyay_drafts | true | false | false |
| nyay_messages | true | false | false |
| nyay_turn_events | true | false | false |
| nyay_turn_executions | true | false | false |

SQL Editor receipt: https://supabase.com/dashboard/project/daojcrxjjkqoirqbvhjn/sql/6e3a278e-f746-4648-95db-76ffc98e94ac

The SQL snippet was not explicitly saved; the source migration in this repository is the durable change record. This manual application does not establish a Supabase CLI migration-history entry. Reconcile the migration history before running CLI push commands; do not reapply the CREATE TABLE statements blindly.

No private case data or credentials were uploaded. No Auth settings, Edge Functions, storage buckets, paid resources, Vercel settings or Vercel deployments were changed. Hosted behavior and advisor checks beyond the displayed schema/grant verification remain outstanding. This is a database foundation, not a completed backend migration.
