import { CreatorSettings } from "@/lib/types";

type PublishSettings = Pick<CreatorSettings, "timezone" | "posting_window_start" | "posting_window_end">;

export type PublishPlan = {
  mode: "now" | "scheduled";
  scheduledFor: string;
  timezone: string;
  summary: string;
  helper: string;
};

function inPostingWindow(settings: PublishSettings, now: Date) {
  const start = settings.posting_window_start;
  const end = settings.posting_window_end;
  if (start === null || end === null || start === end) {
    return true;
  }
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: settings.timezone || "Asia/Kolkata",
    hour: "numeric",
    hour12: false,
  });
  const localHour = Number(formatter.format(now));
  if (start < end) {
    return localHour >= start && localHour < end;
  }
  return localHour >= start || localHour < end;
}

function nextWindowOpen(settings: PublishSettings, now: Date) {
  const start = settings.posting_window_start;
  if (start === null) {
    return now;
  }
  const timezone = settings.timezone || "Asia/Kolkata";
  const localParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
    .format(now)
    .split("-");
  const [year, month, day] = localParts.map(Number);
  const candidate = new Date(Date.UTC(year, month - 1, day, start, 0, 0));
  if (candidate.getTime() <= now.getTime()) {
    candidate.setUTCDate(candidate.getUTCDate() + 1);
  }
  return candidate;
}

export function formatPublishTime(iso: string, timezone: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone || "Asia/Kolkata",
  }).format(new Date(iso));
}

export function getRecommendedPublishPlan(settings: PublishSettings | null | undefined): PublishPlan | null {
  if (!settings) return null;
  const timezone = settings.timezone || "Asia/Kolkata";
  const now = new Date();
  if (inPostingWindow(settings, now)) {
    return {
      mode: "now",
      scheduledFor: now.toISOString(),
      timezone,
      summary: "Post now",
      helper: "This draft is inside your current posting window, so it can move ahead immediately.",
    };
  }
  const scheduled = nextWindowOpen(settings, now);
  return {
    mode: "scheduled",
    scheduledFor: scheduled.toISOString(),
    timezone,
    summary: `Schedule for ${formatPublishTime(scheduled.toISOString(), timezone)}`,
    helper: "This draft is outside your posting window, so Newsbot will hold it until the next allowed slot.",
  };
}
