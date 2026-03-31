-- Migration 003: Customer onboarding and customer-scoped draft generation
-- Run this in Supabase SQL editor (or psql).

-- Draft ownership
alter table draft_posts add column if not exists workspace_user_id bigint references workspace_users(id) on delete cascade;

alter table draft_posts drop constraint if exists draft_posts_event_id_key;
drop index if exists idx_draft_posts_event_id;

create unique index if not exists uq_draft_posts_event_customer_platform
  on draft_posts(event_id, workspace_user_id, platform);
create index if not exists idx_draft_posts_workspace_user_id
  on draft_posts(workspace_user_id);

-- Review ownership
alter table review_queue add column if not exists workspace_user_id bigint references workspace_users(id) on delete cascade;
create index if not exists idx_review_queue_workspace_user_id
  on review_queue(workspace_user_id);

-- Customer-owned profile/settings
create table if not exists customer_profiles (
  id bigserial primary key,
  workspace_user_id bigint not null unique references workspace_users(id) on delete cascade,
  display_name text,
  tone text not null default 'neutral',
  language text not null default 'en',
  watchlist jsonb not null default '[]'::jsonb,
  blocked_phrases jsonb not null default '[]'::jsonb,
  token_store jsonb not null default '{}'::jsonb,
  onboarding_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Customer generation runs
create table if not exists pipeline_runs (
  id bigserial primary key,
  workspace_user_id bigint references workspace_users(id) on delete set null,
  requested_by text not null,
  scope text not null,
  status text not null default 'queued',
  result_counts jsonb not null default '{}'::jsonb,
  error_message text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_pipeline_runs_workspace_user_id
  on pipeline_runs(workspace_user_id);
create index if not exists idx_pipeline_runs_status
  on pipeline_runs(status);

-- RLS alignment
alter table customer_profiles enable row level security;
alter table pipeline_runs enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'customer_profiles' and policyname = 'customer_profiles_service_role_all'
  ) then
    create policy customer_profiles_service_role_all on customer_profiles for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'pipeline_runs' and policyname = 'pipeline_runs_service_role_all'
  ) then
    create policy pipeline_runs_service_role_all on pipeline_runs for all to service_role using (true) with check (true);
  end if;
end
$$;
