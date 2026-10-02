-- 008: lock Evolution's tables (the WhatsApp login lives in evolution_api."Session").
-- Anyone holding that session could use the bot's WhatsApp number, so only the database owner
-- (Evolution and the EzKhata server connect as postgres) may read it. Supabase's public API
-- roles (anon, authenticated) get no access at all, even if the schema is ever exposed.
-- Supabase already encrypts the whole database on disk (AES-256).

begin;

revoke all on schema evolution_api from anon, authenticated;
revoke all on all tables in schema evolution_api from anon, authenticated;
revoke all on all sequences in schema evolution_api from anon, authenticated;
alter default privileges in schema evolution_api revoke all on tables from anon, authenticated;
alter default privileges in schema evolution_api revoke all on sequences from anon, authenticated;

-- Row level security with no policies: API roles see nothing; the owner (postgres) is not affected
do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = 'evolution_api' loop
    execute format('alter table evolution_api.%I enable row level security', r.tablename);
  end loop;
end $$;

commit;
