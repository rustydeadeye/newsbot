-- Migration 001: Production posting improvements
-- Run this in Supabase SQL editor (or psql) before deploying the updated backend.

-- Task: Idempotency key on publish_jobs
alter table publish_jobs add column if not exists idempotency_key text;
create unique index if not exists idx_publish_jobs_idempotency_key
  on publish_jobs(idempotency_key) where idempotency_key is not null;

-- Task: Token persistence + posting windows on creator_settings
alter table creator_settings add column if not exists token_store jsonb not null default '{}'::jsonb;
alter table creator_settings add column if not exists timezone text not null default 'Asia/Kolkata';
alter table creator_settings add column if not exists posting_window_start integer;  -- hour 0-23, null = no restriction
alter table creator_settings add column if not exists posting_window_end integer;    -- hour 0-23, null = no restriction

-- Task: SLA on review_queue
alter table review_queue add column if not exists sla_due_at timestamptz;
create index if not exists idx_review_queue_sla_due_at
  on review_queue(sla_due_at) where status = 'open' and sla_due_at is not null;

-- Task: Engagement stats on publish_logs
alter table publish_logs add column if not exists engagement_stats jsonb not null default '{}'::jsonb;
alter table publish_logs add column if not exists engagement_fetched_at timestamptz;
create index if not exists idx_publish_logs_engagement
  on publish_logs(posted_at) where engagement_fetched_at is null;
