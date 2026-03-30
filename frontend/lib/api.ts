import { CreatorSettings, DraftSummary, EventSummary, PublishJob, PublishLog, ReviewItem, SourceSummary } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function getApiBaseUrl() {
  return API_BASE_URL;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
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

export function getReviewQueue() {
  return fetchJson<ReviewItem[]>("/review");
}

export function getReviewDrafts() {
  return fetchJson<DraftSummary[]>("/review/drafts");
}

export function approveDraft(draftId: number, payload: { reviewer?: string; edited_text?: string; auto_queue?: boolean }) {
  return fetchJson<{ draft: DraftSummary; queued: boolean }>(`/review/drafts/${draftId}/approve`, {
    method: "POST",
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

export function getEvents() {
  return fetchJson<EventSummary[]>("/events");
}

export function getSources() {
  return fetchJson<SourceSummary[]>("/sources");
}

export function getPublishJobs() {
  return fetchJson<PublishJob[]>("/publish-jobs");
}

export function getPublishLogs() {
  return fetchJson<PublishLog[]>("/publish-jobs/logs");
}

export function retryPublishJob(jobId: number) {
  return fetchJson<PublishJob>(`/publish-jobs/${jobId}/retry`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function getCreatorSettings() {
  return fetchJson<CreatorSettings>("/settings/creator");
}

export function updateCreatorSettings(payload: Partial<CreatorSettings>) {
  return fetchJson<CreatorSettings>("/settings/creator", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}
