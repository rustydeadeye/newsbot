-- Migration 004: Customer daily-use lifecycle, automation, and history settings

alter table customer_profiles
  add column if not exists automation_mode text not null default 'auto_generate_manual_review',
  add column if not exists freshness_window_hours integer not null default 12,
  add column if not exists max_posts_per_hour integer not null default 6,
  add column if not exists timezone text not null default 'Asia/Kolkata',
  add column if not exists posting_window_start integer,
  add column if not exists posting_window_end integer,
  add column if not exists auto_post_enabled boolean not null default false,
  add column if not exists auto_post_threshold integer not null default 85,
  add column if not exists last_seen_at timestamptz;
