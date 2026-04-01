create table if not exists sources (
  id bigserial primary key,
  name text unique not null,
  type text not null,
  base_url text not null,
  poll_interval_sec integer not null default 300,
  enabled boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_items (
  id bigserial primary key,
  source_id bigint not null references sources(id) on delete cascade,
  external_id text not null,
  url text not null,
  title text not null,
  published_at timestamptz,
  raw_payload jsonb not null,
  checksum text not null,
  processed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_source_items_checksum on source_items(checksum);
create index if not exists idx_source_items_unprocessed on source_items(id) where not processed;
create index if not exists idx_source_items_source_id on source_items(source_id);

create table if not exists events (
  id bigserial primary key,
  source_item_id bigint references source_items(id) on delete set null,
  event_type text not null,
  entity_type text,
  entity_name text,
  ticker text,
  source_priority integer not null default 0,
  occurred_at timestamptz,
  summary_facts jsonb not null,
  importance_score double precision not null default 0,
  confidence_score double precision not null default 0,
  dedupe_key text unique not null,
  status text not null default 'new',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists event_entities (
  id bigserial primary key,
  event_id bigint not null references events(id) on delete cascade,
  entity_type text not null,
  entity_name text not null,
  ticker text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_events_source_item_id on events(source_item_id);
create index if not exists idx_event_entities_event_id on event_entities(event_id);

create table if not exists draft_posts (
  id bigserial primary key,
  event_id bigint not null references events(id) on delete cascade,
  workspace_user_id bigint references workspace_users(id) on delete cascade,
  platform text not null default 'x',
  status text not null default 'draft',
  prompt_version text not null default 'v1',
  draft_text text not null,
  safety_flags jsonb not null default '{}'::jsonb,
  needs_review boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists uq_draft_posts_event_customer_platform
  on draft_posts(event_id, workspace_user_id, platform);
create index if not exists idx_draft_posts_workspace_user_id on draft_posts(workspace_user_id);

create table if not exists publish_jobs (
  id bigserial primary key,
  draft_post_id bigint not null references draft_posts(id) on delete cascade,
  status text not null default 'queued',
  scheduled_for timestamptz,
  attempt_count integer not null default 0,
  last_error text,
  result_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_publish_jobs_draft_post_id on publish_jobs(draft_post_id);

alter table publish_jobs add column if not exists result_message text;

create table if not exists publish_logs (
  id bigserial primary key,
  publish_job_id bigint not null references publish_jobs(id) on delete cascade,
  platform_post_id text,
  posted_at timestamptz,
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_publish_logs_publish_job_id on publish_logs(publish_job_id);

create table if not exists creator_settings (
  id bigserial primary key,
  display_name text not null,
  primary_platform text not null default 'x',
  tone text not null default 'neutral',
  language text not null default 'en',
  max_posts_per_hour integer not null default 6,
  watchlist jsonb not null default '[]'::jsonb,
  blocked_phrases jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists workspace_users (
  id bigserial primary key,
  auth_user_id text not null unique,
  email text not null unique,
  display_name text,
  role text not null default 'customer' check (role in ('admin', 'customer')),
  is_active boolean not null default true,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_workspace_users_role on workspace_users(role);

create table if not exists customer_profiles (
  id bigserial primary key,
  workspace_user_id bigint not null unique references workspace_users(id) on delete cascade,
  display_name text,
  tone text not null default 'neutral',
  language text not null default 'en',
  watchlist jsonb not null default '[]'::jsonb,
  blocked_phrases jsonb not null default '[]'::jsonb,
  token_store jsonb not null default '{}'::jsonb,
  automation_mode text not null default 'auto_generate_manual_review',
  freshness_window_hours integer not null default 12,
  max_posts_per_hour integer not null default 6,
  timezone text not null default 'Asia/Kolkata',
  posting_window_start integer,
  posting_window_end integer,
  auto_post_enabled boolean not null default false,
  auto_post_threshold integer not null default 85,
  last_seen_at timestamptz,
  onboarding_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists review_queue (
  id bigserial primary key,
  event_id bigint not null references events(id) on delete cascade,
  workspace_user_id bigint references workspace_users(id) on delete cascade,
  reason text not null,
  assigned_to text,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_review_queue_event_id on review_queue(event_id);
create index if not exists idx_review_queue_workspace_user_id on review_queue(workspace_user_id);

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
create index if not exists idx_pipeline_runs_workspace_user_id on pipeline_runs(workspace_user_id);
create index if not exists idx_pipeline_runs_status on pipeline_runs(status);

alter table sources enable row level security;
alter table source_items enable row level security;
alter table events enable row level security;
alter table event_entities enable row level security;
alter table draft_posts enable row level security;
alter table publish_jobs enable row level security;
alter table publish_logs enable row level security;
alter table creator_settings enable row level security;
alter table customer_profiles enable row level security;
alter table workspace_users enable row level security;
alter table review_queue enable row level security;
alter table pipeline_runs enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'sources' and policyname = 'sources_service_role_all'
  ) then
    create policy sources_service_role_all on sources for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'source_items' and policyname = 'source_items_service_role_all'
  ) then
    create policy source_items_service_role_all on source_items for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'events' and policyname = 'events_service_role_all'
  ) then
    create policy events_service_role_all on events for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'event_entities' and policyname = 'event_entities_service_role_all'
  ) then
    create policy event_entities_service_role_all on event_entities for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'draft_posts' and policyname = 'draft_posts_service_role_all'
  ) then
    create policy draft_posts_service_role_all on draft_posts for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'publish_jobs' and policyname = 'publish_jobs_service_role_all'
  ) then
    create policy publish_jobs_service_role_all on publish_jobs for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'publish_logs' and policyname = 'publish_logs_service_role_all'
  ) then
    create policy publish_logs_service_role_all on publish_logs for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'creator_settings' and policyname = 'creator_settings_service_role_all'
  ) then
    create policy creator_settings_service_role_all on creator_settings for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'customer_profiles' and policyname = 'customer_profiles_service_role_all'
  ) then
    create policy customer_profiles_service_role_all on customer_profiles for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'workspace_users' and policyname = 'workspace_users_service_role_all'
  ) then
    create policy workspace_users_service_role_all on workspace_users for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'review_queue' and policyname = 'review_queue_service_role_all'
  ) then
    create policy review_queue_service_role_all on review_queue for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'pipeline_runs' and policyname = 'pipeline_runs_service_role_all'
  ) then
    create policy pipeline_runs_service_role_all on pipeline_runs for all to service_role using (true) with check (true);
  end if;
end
$$;

insert into sources (name, type, base_url, poll_interval_sec, enabled, metadata)
values
  ('rbi_press_releases', 'rss', 'https://rbi.org.in/pressreleases_rss.xml', 300, true, '{"priority": 100}'),
  ('sebi_releases', 'rss', 'https://www.sebi.gov.in/sebirss.xml', 600, true, '{"priority": 90}'),
  ('nse_corporate_filings', 'html', 'https://www.nseindia.com/companies-listing/corporate-filings-application', 180, true, '{"priority": 95}'),
  ('bse_announcements', 'rss', 'https://www.bseindia.com/data/xml/announcements.xml', 180, true, '{"priority": 95}'),
  ('pib_economy', 'rss', 'https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=31', 600, true, '{"priority": 80}'),
  ('mospi_releases', 'html', 'https://mospi.gov.in/press-release?date_filter%5Bmax%5D=&date_filter%5Bmin%5D=&field_press_release_category_tid=All&order=title&page=0&sort=desc', 1800, true, '{"priority": 85}')
on conflict (name) do nothing;
