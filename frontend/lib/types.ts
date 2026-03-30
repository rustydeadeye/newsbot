import { ViewerProfile } from "@/lib/session";

export type EventSummary = {
  id: number;
  event_type: string;
  entity_name: string | null;
  ticker: string | null;
  importance_score: number;
  confidence_score: number;
  dedupe_key?: string;
  summary_facts: Record<string, unknown>;
  status?: string;
};

export type DraftSummary = {
  id: number;
  event_id: number;
  platform: string;
  status: string;
  prompt_version: string;
  draft_text: string;
  safety_flags: Record<string, unknown>;
  needs_review: boolean;
  event?: EventSummary | null;
};

export type ReviewItem = {
  id: number;
  event_id: number;
  reason: string;
  assigned_to: string | null;
  status: string;
  event: EventSummary | null;
  draft: DraftSummary | null;
};

export type SourceSummary = {
  id: number;
  name: string;
  type: string;
  base_url: string;
  poll_interval_sec: number;
  enabled: boolean;
};

export type PublishJob = {
  id: number;
  draft_post_id: number;
  status: string;
  scheduled_for: string | null;
  attempt_count: number;
  last_error: string | null;
  result_message?: string | null;
  created_at: string | null;
  updated_at: string | null;
  draft: DraftSummary | null;
  event: EventSummary | null;
};

export type PublishLog = {
  id: number;
  publish_job_id: number;
  platform_post_id: string | null;
  posted_at: string | null;
  response_payload: Record<string, unknown>;
  created_at: string | null;
};

export type CreatorSettings = {
  id: number;
  display_name: string;
  primary_platform: string;
  tone: string;
  language: string;
  max_posts_per_hour: number;
  watchlist: string[];
  blocked_phrases: string[];
};

export type AuthMeResponse = {
  viewer: ViewerProfile;
};
