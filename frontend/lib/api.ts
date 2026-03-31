import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import { AuthMeResponse, CreatorSettings, DraftSummary, EventSummary, PublishJob, PublishLog, ReviewItem, SourceSummary } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function getApiBaseUrl() {
  return API_BASE_URL;
}

type FetchJsonOptions = RequestInit & {
  accessToken?: string | null;
};

async function getAccessToken(accessToken?: string | null) {
  if (accessToken) {
    return accessToken;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const supabase = getSupabaseBrowserClient();
  const {
    data: { session }
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

async function fetchJson<T>(path: string, init?: FetchJsonOptions): Promise<T> {
  const accessToken = await getAccessToken(init?.accessToken);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(init?.headers ?? {})
      },
      cache: "no-store"
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown fetch error";
    throw new Error(`API request failed for ${path} via ${API_BASE_URL}: ${detail}`);
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API request failed for ${path} via ${API_BASE_URL}: ${response.status} ${detail}`);
  }

  return response.json() as Promise<T>;
}

export function getReviewQueue(accessToken?: string | null) {
  return fetchJson<ReviewItem[]>("/review", { accessToken });
}

export function getReviewDrafts(accessToken?: string | null) {
  return fetchJson<DraftSummary[]>("/review/drafts", { accessToken });
}

export function getRejectedDrafts(accessToken?: string | null) {
  return fetchJson<DraftSummary[]>("/review/drafts/rejected", { accessToken });
}

export function reopenDraft(draftId: number) {
  return fetchJson<DraftSummary>(`/review/drafts/${draftId}/reopen`, {
    method: "POST"
  });
}

export function approveDraft(draftId: number, payload: { reviewer?: string; edited_text?: string; auto_queue?: boolean }) {
  return fetchJson<{ draft: DraftSummary; queued: boolean; warning?: string }>(`/review/drafts/${draftId}/approve`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function patchSource(sourceId: number, payload: { enabled: boolean }) {
  return fetchJson<{ id: number; name: string; enabled: boolean }>(`/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function rejectDraft(draftId: number, payload: { reviewer?: string; reason: string }) {
  return fetchJson<{ draft: DraftSummary }>(`/review/drafts/${draftId}/reject`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function resolveReviewItem(reviewId: number, payload: { reviewer?: string; status?: string }) {
  return fetchJson<ReviewItem>(`/review/items/${reviewId}/resolve`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getEvents(accessToken?: string | null) {
  return fetchJson<EventSummary[]>("/events", { accessToken });
}

export function getSources(accessToken?: string | null) {
  return fetchJson<SourceSummary[]>("/sources", { accessToken });
}

export function getPublishJobs(accessToken?: string | null) {
  return fetchJson<PublishJob[]>("/publish-jobs", { accessToken });
}

export function getPublishLogs(accessToken?: string | null) {
  return fetchJson<PublishLog[]>("/publish-jobs/logs", { accessToken });
}

export function retryPublishJob(jobId: number) {
  return fetchJson<PublishJob>(`/publish-jobs/${jobId}/retry`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function cancelPublishJob(jobId: number) {
  return fetchJson<PublishJob>(`/publish-jobs/${jobId}/cancel`, {
    method: "POST"
  });
}

export function runPipeline() {
  return fetchJson<{ ingested: Record<string, number>; normalized: number; drafted: number; queued: number; posted: number }>("/pipeline/run", {
    method: "POST"
  });
}

export function getCreatorSettings(accessToken?: string | null) {
  return fetchJson<CreatorSettings>("/settings/creator", { accessToken });
}

export function updateCreatorSettings(payload: Partial<CreatorSettings>) {
  return fetchJson<CreatorSettings>("/settings/creator", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getXConnectUrl(accessToken?: string | null) {
  return fetchJson<{ auth_url: string }>("/settings/x/connect", { accessToken });
}

export function getAuthMe(accessToken: string) {
  return fetchJson<AuthMeResponse>("/auth/me", { accessToken });
}
