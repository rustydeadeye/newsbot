create table if not exists wire_candidates (
  id bigserial primary key,
  source_name text not null,
  external_id text not null unique,
  title text not null,
  ticker text,
  event_type text not null,
  dedupe_key text not null,
  published_at timestamptz,
  importance_score integer not null default 0,
  confidence_score double precision not null default 0,
  draft_text text not null,
  raw_payload jsonb not null default '{}'::jsonb,
  last_action text,
  last_reason text,
  last_scheduled_for timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_wire_candidates_dedupe_key on wire_candidates(dedupe_key);
create index if not exists idx_wire_candidates_ticker on wire_candidates(ticker);

create table if not exists wire_jobs (
  id bigserial primary key,
  candidate_id bigint not null references wire_candidates(id) on delete cascade,
  status text not null default 'queued',
  priority text not null default 'normal',
  scheduled_for timestamptz,
  attempt_count integer not null default 0,
  last_error text,
  result_message text,
  idempotency_key text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_wire_jobs_candidate_id on wire_jobs(candidate_id);
create index if not exists idx_wire_jobs_status_scheduled_for on wire_jobs(status, scheduled_for);

create table if not exists wire_publish_logs (
  id bigserial primary key,
  wire_job_id bigint not null references wire_jobs(id) on delete cascade,
  platform_post_id text,
  posted_at timestamptz,
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_wire_publish_logs_wire_job_id on wire_publish_logs(wire_job_id);

alter table wire_candidates enable row level security;
alter table wire_jobs enable row level security;
alter table wire_publish_logs enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'wire_candidates' and policyname = 'wire_candidates_service_role_all'
  ) then
    create policy wire_candidates_service_role_all on wire_candidates for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'wire_jobs' and policyname = 'wire_jobs_service_role_all'
  ) then
    create policy wire_jobs_service_role_all on wire_jobs for all to service_role using (true) with check (true);
  end if;

  if not exists (
    select 1 from pg_policies where schemaname = 'public' and tablename = 'wire_publish_logs' and policyname = 'wire_publish_logs_service_role_all'
  ) then
    create policy wire_publish_logs_service_role_all on wire_publish_logs for all to service_role using (true) with check (true);
  end if;
end
$$;
