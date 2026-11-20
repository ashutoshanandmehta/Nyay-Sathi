-- Read-only hosted-schema verification, also used after the dashboard migration.
select c.relname as table_name,
       c.relrowsecurity as rls_enabled,
       has_table_privilege('anon', c.oid, 'SELECT') as anonymous_can_read,
       has_table_privilege('authenticated', c.oid, 'INSERT') as client_can_insert
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and c.relname like 'nyay_%'
order by c.relname;
