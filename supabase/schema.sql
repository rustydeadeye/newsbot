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

create table if not exists draft_posts (
  id bigserial primary key,
  event_id bigint not null unique references events(id) on delete cascade,
  platform text not null default 'x',
  status text not null default 'draft',
  prompt_version text not null default 'v1',
  draft_text text not null,
  safety_flags jsonb not null default '{}'::jsonb,
  needs_review boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists publish_jobs (
  id bigserial primary key,
  draft_post_id bigint not null references draft_posts(id) on delete cascade,
  status text not null default 'queued',
  scheduled_for timestamptz,
  attempt_count integer not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists publish_logs (
  id bigserial primary key,
  publish_job_id bigint not null references publish_jobs(id) on delete cascade,
  platform_post_id text,
  posted_at timestamptz,
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

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

create table if not exists review_queue (
  id bigserial primary key,
  event_id bigint not null references events(id) on delete cascade,
  reason text not null,
  assigned_to text,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into sources (name, type, base_url, poll_interval_sec, enabled, metadata)
values
  ('rbi_press_releases', 'rss', 'https://rbi.org.in/pressreleases_rss.xml', 300, true, '{"priority": 100}'),
  ('sebi_releases', 'rss', 'https://www.sebi.gov.in/sebirss.xml', 600, true, '{"priority": 90}'),
  ('nse_corporate_filings', 'html', 'https://www.nseindia.com/companies-listing/corporate-filings-application', 180, true, '{"priority": 95}'),
  ('bse_announcements', 'rss', 'https://www.bseindia.com/data/xml/announcements.xml', 180, true, '{"priority": 95}'),
  ('pib_economy', 'rss', 'https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=31', 600, true, '{"priority": 80}'),
  ('mospi_releases', 'html', 'https://mospi.gov.in/press-release?date_filter%5Bmax%5D=&date_filter%5Bmin%5D=&field_press_release_category_tid=All&order=title&page=0&sort=desc', 1800, true, '{"priority": 85}')
on conflict (name) do nothing;
