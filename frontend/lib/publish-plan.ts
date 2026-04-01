import { CreatorSettings } from "@/lib/types";

type PublishSettings = Pick<CreatorSettings, "timezone" | "posting_window_start" | "posting_window_end">;

export type PublishPlan = {
  mode: "now" | "scheduled";
  scheduledFor: string;
  timezone: string;
  summary: string;
  helper: string;
};

function getSafeTimeZone(timezone?: string | null) {
  const value = timezone || "Asia/Kolkata";
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: value }).format(new Date());
    return value;
  } catch {
    return "Asia/Kolkata";
  }
}

export function parseIsoDate(value?: string | null) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function toIsoString(value?: string | null) {
  const parsed = parseIsoDate(value);
  return parsed ? parsed.toISOString() : null;
}

function inPostingWindow(settings: PublishSettings, now: Date) {
  const start = settings.posting_window_start;
  const end = settings.posting_window_end;
  if (start === null || end === null || start === end) {
    return true;
  }
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: getSafeTimeZone(settings.timezone),
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
  const timezone = getSafeTimeZone(settings.timezone);
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
  const parsed = parseIsoDate(iso);
  if (!parsed) {
    return "Time unavailable";
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: getSafeTimeZone(timezone),
    }).format(parsed);
  } catch {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Kolkata",
    }).format(parsed);
  }
}

export function getRecommendedPublishPlan(settings: PublishSettings | null | undefined): PublishPlan | null {
  if (!settings) return null;
  const timezone = getSafeTimeZone(settings.timezone);
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
