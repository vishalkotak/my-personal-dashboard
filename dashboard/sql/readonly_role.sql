-- Read-only database login for the local dashboard.
--
-- Run this ONCE in Supabase -> SQL Editor (it's safe to run again later, e.g. to rotate
-- the password). Before running:
--
--   1. Generate a strong password on your Mac:     openssl rand -base64 32
--   2. Paste it in place of REPLACE_WITH_A_STRONG_PASSWORD below (keep the quotes).
--      If the password contains a single quote ', write it twice ''.
--   3. Run. Then delete the password from the editor tab / don't save it as a snippet.
--
-- What this role can do: SELECT on public.health_samples. Nothing else.
--   * no INSERT / UPDATE / DELETE / TRUNCATE grants, on anything
--   * every session is read-only by default and queries are cut off after 15 s
--   * it can't see any other table (auth.users, etc.)
--
-- Heads-up: the policy below lets this role read EVERY user's rows in health_samples,
-- not just yours. That's fine for a personal, single-owner Supabase project (it's the
-- point: the dashboard shows all of your data, including rows from an older anonymous
-- account if the app ever had to create a new one). If you ever share the project with
-- other people, set HEALTH_USER_ID in dashboard/.env, or tighten the policy to
-- `using (user_id = '<your-uuid>')`.
--
-- Connecting (Supabase session pooler, IPv4-friendly; the free tier's direct
-- connection is IPv6-only). Note the username is <role>.<project-ref>:
--
--   postgresql://healthsync_reader.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
--
-- Find <project-ref> and <region> under Project Settings -> Database -> Connection string
-- -> "Session pooler". URL-encode the password if it contains / + = @ : (or generate one
-- with `openssl rand -hex 32`, which only contains 0-9a-f).

do $$
declare
  pw text := 'REPLACE_WITH_A_STRONG_PASSWORD';
begin
  if pw like 'REPLACE\_WITH%' or length(pw) < 20 then
    raise exception 'Set a real password first (openssl rand -base64 32), at least 20 characters.';
  end if;

  if not exists (select from pg_roles where rolname = 'healthsync_reader') then
    -- A plain login role: not a superuser, can't create roles or databases, no RLS bypass
    -- (those are all the defaults; Supabase won't let you grant them anyway).
    execute format('create role healthsync_reader with login noinherit connection limit 10 password %L', pw);
  else
    execute format('alter role healthsync_reader with login password %L', pw);
  end if;
end
$$;

-- Sessions are read-only and can't run away.
alter role healthsync_reader set default_transaction_read_only = on;
alter role healthsync_reader set statement_timeout = '15s';
alter role healthsync_reader set idle_in_transaction_session_timeout = '30s';

-- Least privilege: clear anything it may have picked up, then grant exactly one thing.
revoke all on all tables in schema public from healthsync_reader;
revoke all on all sequences in schema public from healthsync_reader;
grant usage on schema public to healthsync_reader;
grant select on table public.health_samples to healthsync_reader;
-- Deliberately NO insert, update, delete or truncate.

-- Row-Level Security is enabled on health_samples, so without a policy this role would
-- see zero rows. This policy lets it read; there is no policy for writing.
drop policy if exists "dashboard reader can read all samples" on public.health_samples;
create policy "dashboard reader can read all samples" on public.health_samples
  for select to healthsync_reader using (true);

-- Check: exactly one row, SELECT on public.health_samples ...
select table_schema, table_name, privilege_type
from information_schema.role_table_grants
where grantee = 'healthsync_reader';

-- ... and every attribute below should be false.
select rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
from pg_roles where rolname = 'healthsync_reader';
