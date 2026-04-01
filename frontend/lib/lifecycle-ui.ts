import { CreatorSettings, DraftSummary, ReviewItem } from "@/lib/types";
import { formatPublishTime, getRecommendedPublishPlan } from "@/lib/publish-plan";

function formatLocalTime(iso: string, timezone?: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone || "Asia/Kolkata",
  }).format(new Date(iso));
}

export function getFreshnessLabel(item: Pick<ReviewItem | DraftSummary, "lifecycle_state" | "fresh_until">, timezone?: string) {
  if (item.lifecycle_state === "scheduled") {
    return "Scheduled, but will expire if it becomes stale before posting";
  }
  if (item.lifecycle_state === "overdue") {
    return "Still actionable, but aging out soon";
  }
  if (item.lifecycle_state === "fresh" && item.fresh_until) {
    return `Fresh until ${formatLocalTime(item.fresh_until, timezone)}`;
  }
  return null;
}

export function getFreshnessTone(item: Pick<ReviewItem | DraftSummary, "lifecycle_state">) {
  if (item.lifecycle_state === "overdue") return "warn";
  if (item.lifecycle_state === "scheduled") return "subtle";
  return "calm";
}

export function getInactiveReasonCopy(reason?: string | null) {
  if (!reason) return null;
  if (reason === "expired_by_age") return "Expired before action";
  if (reason === "superseded_by_newer_update") return "Replaced by a newer update";
  if (reason === "expired_before_publish") return "Expired before publish";
  if (reason === "cancelled_by_customer") return "Moved back to approved";
  return reason.replaceAll("_", " ");
}

export function getActivityLabel(status: string) {
  if (status === "failed") return "Delivery failed";
  if (status === "expired") return "Expired before review";
  if (status === "superseded") return "Superseded by a newer update";
  if (status === "posted") return "Posted successfully";
  if (status === "rejected") return "Rejected";
  return status.replaceAll("_", " ");
}

export function getModeExplanation(settings: CreatorSettings) {
  if (settings.automation_mode === "manual_review_only") {
    return "Newsbot will wait for you to generate drafts manually. Nothing will publish automatically.";
  }
  if (settings.automation_mode === "auto_generate_auto_post_high_confidence") {
    return "Newsbot can generate drafts in the background and only selected macro or regulatory items may auto-post.";
  }
  return "Newsbot will generate drafts in the background, but nothing will publish automatically.";
}

export function getModeLabel(mode?: string) {
  if (mode === "manual_review_only") return "Manual";
  if (mode === "auto_generate_auto_post_high_confidence") return "Auto-create drafts and auto-post selected macro/regulatory items";
  return "Auto-create drafts for review";
}

export function getDependencyMessage(settings: CreatorSettings) {
  if (!settings.openai_configured) {
    return "Background generation cannot run until your OpenAI key is configured.";
  }
  if (settings.automation_mode === "auto_generate_auto_post_high_confidence" && !settings.x_connected) {
    return "Auto-post is disabled until you connect your X account.";
  }
  return null;
}

export function getAutomationStatusCopy(settings: CreatorSettings) {
  if (!settings.openai_configured) {
    return "Selected mode is currently blocked because your OpenAI key is missing.";
  }
  if (settings.automation_mode === "auto_generate_auto_post_high_confidence" && !settings.x_connected) {
    return "Selected mode is partially blocked until your X account is connected.";
  }
  return "Selected mode is active.";
}

export function getNextAvailableSlot(settings: CreatorSettings) {
  const plan = getRecommendedPublishPlan(settings);
  if (!plan) return null;
  return {
    iso: plan.scheduledFor,
    label: plan.mode === "now" ? "Next available slot is now" : `Next available slot: ${formatPublishTime(plan.scheduledFor, plan.timezone)}`,
    helper: plan.helper,
  };
}

export function getBucketLabel(status?: string | null, lifecycleState?: string | null) {
  const value = lifecycleState || status || "";
  if (value === "fresh" || value === "overdue" || value === "draft") return "Needs action";
  if (value === "approved") return "Ready to publish";
  if (value === "queued" || value === "publishing" || value === "scheduled") return "Scheduled";
  if (value === "posted") return "Posted";
  if (value === "failed") return "Needs attention";
  return "History";
}
