import { ViewerProfile } from "@/lib/session";

export type WireProduct = "finance" | "ai";

export type WireJobStatus = "queued" | "publishing" | "failed" | "skipped" | "cancelled" | "posted";

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
  draft_id: number | null;
  draft_status: string | null;
};

export type DraftSummary = {
  id: number;
  event_id: number;
  workspace_user_id?: number | null;
  platform: string;
  status: string;
  prompt_version: string;
  draft_text: string;
  safety_flags: Record<string, unknown>;
  needs_review: boolean;
  lifecycle_state?: string;
  inactive_reason?: string | null;
  fresh_until?: string | null;
  updated_at?: string | null;
  publish_job?: PublishJob | null;
  event?: EventSummary | null;
};

export type ReviewItem = {
  id: number;
  event_id: number;
  reason: string;
  assigned_to: string | null;
  status: string;
  sla_due_at: string | null;
  overdue: boolean;
  lifecycle_state?: string;
  inactive_reason?: string | null;
  fresh_until?: string | null;
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
  engagement_stats: Record<string, unknown>;
  engagement_fetched_at: string | null;
  created_at: string | null;
};

export type WireCandidateSummary = {
  id: number;
  customer_profile_id?: number;
  source_name: string;
  external_id: string;
  title: string;
  ticker: string | null;
  event_type: string;
  dedupe_key: string;
  importance_score: number;
  confidence_score: number;
  draft_text: string;
  published_at: string | null;
  last_action: string | null;
  last_reason: string | null;
  last_scheduled_for: string | null;
  product?: WireProduct;
  source_family?: string;
  lane?: string | null;
};

export type WireJob = {
  id: number;
  candidate_id: number;
  status: WireJobStatus;
  priority: string;
  scheduled_for: string | null;
  attempt_count: number;
  last_error: string | null;
  result_message: string | null;
  idempotency_key: string | null;
  created_at: string | null;
  updated_at: string | null;
  candidate: WireCandidateSummary | null;
};

export type WirePublishLog = {
  id: number;
  wire_job_id: number;
  platform_post_id: string | null;
  posted_at: string | null;
  response_payload: Record<string, unknown>;
  created_at: string | null;
  job: {
    id: number;
    status: string;
    priority: string;
    scheduled_for: string | null;
  } | null;
  candidate: {
    id: number;
    title: string;
    ticker: string | null;
    draft_text: string;
    source_name: string;
    product?: string;
    source_family?: string;
    lane?: string | null;
  } | null;
};

export type CreatorSettings = {
  id: number;
  display_name: string;
  wire_product?: string;
  primary_platform: string;
  tone: string;
  language: string;
  max_posts_per_hour: number;
  automation_mode?: string;
  freshness_window_hours?: number;
  watchlist: string[];
  blocked_phrases: string[];
  timezone: string;
  posting_window_start: number | null;
  posting_window_end: number | null;
  x_connected: boolean;
  openai_configured: boolean;
  tavily_configured?: boolean;
  auto_post_enabled?: boolean;
  auto_post_threshold?: number;
  last_seen_at?: string | null;
};

export type OnboardingStatus = {
  id: number;
  workspace_user_id: number;
  display_name: string | null;
  tone: string;
  language: string;
  watchlist: string[];
  blocked_phrases: string[];
  openai_configured: boolean;
  tavily_configured?: boolean;
  x_connected: boolean;
  onboarding_completed: boolean;
  onboarding_completed_at: string | null;
  publishing_ready: boolean;
  required: boolean;
  missing: string[];
};

export type AutopostDashboard = {
  display_name: string | null;
  wire_product: string;
  wire_product_label: string;
  x_connected: boolean;
  openai_configured: boolean;
  tavily_configured: boolean;
  publishing_ready: boolean;
  autopost_enabled: boolean;
  status: "setup_required" | "paused" | "active" | "needs_attention";
  posting_window: {
    start_hour: number;
    end_hour: number;
    timezone: string;
  };
  quiet_hours: {
    start_hour: number;
    end_hour: number;
    timezone: string;
  };
  scan_interval_minutes: number;
  next_posts: {
    id: number;
    status: string;
    scheduled_for: string | null;
    tweet_text: string;
    source_title: string;
    ticker: string | null;
    source_name: string;
    product: string;
    source_family: string;
    lane: string | null;
  }[];
  recent_posts: {
    id: number;
    platform_post_id: string | null;
    posted_at: string | null;
    tweet_text: string | null;
    source_title: string | null;
    ticker: string | null;
    source_name: string | null;
    product: string;
    source_family: string;
    lane: string | null;
    x_url: string | null;
  }[];
};

export type CustomerWorkspaceState =
  | "onboarding_incomplete"
  | "ready_to_generate"
  | "generation_in_progress"
  | "generation_no_matches"
  | "generation_ready"
  | "temporary_issue";

export type PipelineRun = {
  id: number;
  workspace_user_id: number | null;
  requested_by: string;
  scope: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  result_counts: Record<string, number>;
  error_message: string | null;
};

export type AuthMeResponse = {
  viewer: ViewerProfile;
};

export type CustomerHomePayload = {
  queue: ReviewItem[];
  approved_drafts: DraftSummary[];
  settings: CreatorSettings;
  since_last_seen_at?: string | null;
  since_last_seen_summary: Record<string, number>;
  recent_activity: {
    draft_id: number;
    status: string;
    headline: string;
    updated_at: string | null;
    inactive_reason?: string | null;
  }[];
};

export type CustomerDraftsPayload = {
  drafts: DraftSummary[];
  approved_drafts: DraftSummary[];
  rejected_drafts: DraftSummary[];
  history: DraftSummary[];
  settings: CreatorSettings;
};
