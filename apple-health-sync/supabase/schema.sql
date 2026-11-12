-- HealthSync schema. Run once in Supabase → SQL Editor.
-- Security model:
--   * The app only ever holds the publishable (anon) key, which is public by design.
--   * Row-Level Security guarantees each signed-in user can only touch their own rows.
--   * Rows are immutable: there is no UPDATE grant or policy, so a stolen session
--     can't silently rewrite history (HealthKit samples never change either).

create table if not exists public.health_samples (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  hk_uuid     uuid not null,                       -- HealthKit's sample UUID (idempotency key)
  type        text not null,                       -- e.g. HKQuantityTypeIdentifierHeartRate
  start_date  timestamptz not null,
  end_date    timestamptz not null,
  value       double precision not null,
  unit        text not null,
  metadata    jsonb not null default '{}'::jsonb,
  uploaded_at timestamptz not null default now(),
  unique (user_id, hk_uuid)
);

-- Abuse limits. Anonymous sign-ups are open (anyone holding the public key can create an account),
-- so cap what a single row can hold to stop junk data from filling the free-tier quota.
alter table public.health_samples drop constraint if exists health_samples_limits;
alter table public.health_samples add constraint health_samples_limits check (
      char_length(type) <= 128
  and char_length(unit) <= 32
  and pg_column_size(metadata) <= 4096
  and end_date >= start_date
);

create index if not exists health_samples_user_type_start
  on public.health_samples (user_id, type, start_date desc);

alter table public.health_samples enable row level security;

-- Least privilege: anonymous callers get nothing; signed-in users get select/insert/delete only.
revoke all on public.health_samples from anon, authenticated;
grant select, insert, delete on public.health_samples to authenticated;

create policy "read own samples"   on public.health_samples
  for select to authenticated using ((select auth.uid()) = user_id);

create policy "insert own samples" on public.health_samples
  for insert to authenticated with check ((select auth.uid()) = user_id);

create policy "delete own samples" on public.health_samples
  for delete to authenticated using ((select auth.uid()) = user_id);
