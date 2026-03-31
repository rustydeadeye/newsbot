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

export type CreatorSettings = {
  id: number;
  display_name: string;
  primary_platform: string;
  tone: string;
  language: string;
  max_posts_per_hour: number;
  watchlist: string[];
  blocked_phrases: string[];
  timezone: string;
  posting_window_start: number | null;
  posting_window_end: number | null;
  x_connected: boolean;
  openai_configured: boolean;
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
  x_connected: boolean;
  onboarding_completed: boolean;
  onboarding_completed_at: string | null;
  publishing_ready: boolean;
  required: boolean;
  missing: string[];
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
};

export type CustomerDraftsPayload = {
  drafts: DraftSummary[];
  approved_drafts: DraftSummary[];
  rejected_drafts: DraftSummary[];
  settings: CreatorSettings;
};
