-- Apply manually only to the approved Nyay Saathi project after creating a
-- Vault secret named nyay_resumable_worker_bearer. Match NYAY_WORKER_SECRET.
-- Enable pg_cron and pg_net using the dashboard first.
select cron.schedule('nyay-resumable-sweep','5 seconds', $job$
  select net.http_post(
    url := 'https://daojcrxjjkqoirqbvhjn.supabase.co/functions/v1/nyay-api/internal/resumable/sweep',
    headers := jsonb_build_object(
      'Content-Type','application/json',
      'Authorization','Bearer ' || (select decrypted_secret from vault.decrypted_secrets
        where name = 'nyay_resumable_worker_bearer')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 34000
  )
  where exists(select 1 from public.nyay_turn_work where due_at<=now()
    and (lease_until is null or lease_until<=now()));
$job$);
select cron.schedule('nyay-resumable-webhook-cleanup','13 2 * * *',$job$
  delete from public.nyay_turn_webhook_receipts where received_at < now() - interval '7 days';
$job$);
