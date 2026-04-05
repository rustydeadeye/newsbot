import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import { AuthMeResponse, AutopostDashboard, WireJob, WirePublishLog } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function getApiBaseUrl() {
  return API_BASE_URL;
}

type FetchJsonOptions = RequestInit & {
  accessToken?: string | null;
};

type ProfileSettingsUpdate = {
  display_name?: string;
  auto_post_enabled?: boolean;
  wire_product?: "finance" | "ai";
  openai_api_key?: string;
  tavily_api_key?: string;
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

export function getWireJobs(accessToken?: string | null) {
  return fetchJson<WireJob[]>("/publish-jobs/wire", { accessToken });
}

export function getWireLogs(accessToken?: string | null) {
  return fetchJson<WirePublishLog[]>("/publish-jobs/wire/logs", { accessToken });
}

export function retryWireJob(jobId: number) {
  return fetchJson<WireJob>(`/publish-jobs/wire/${jobId}/retry`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function cancelWireJob(jobId: number) {
  return fetchJson<WireJob>(`/publish-jobs/wire/${jobId}/cancel`, {
    method: "POST"
  });
}

export function getAutopostDashboard(accessToken?: string | null) {
  return fetchJson<AutopostDashboard>("/settings/autopost", { accessToken });
}

export function pauseAutopost() {
  return fetchJson<AutopostDashboard>("/settings/autopost/pause", {
    method: "POST"
  });
}

export function resumeAutopost() {
  return fetchJson<AutopostDashboard>("/settings/autopost/resume", {
    method: "POST"
  });
}

export function disconnectXAccount() {
  return fetchJson<{ x_connected: boolean; autopost_enabled?: boolean }>("/settings/x/disconnect", {
    method: "POST"
  });
}

export function updateProfileSettings(payload: ProfileSettingsUpdate) {
  return fetchJson<{
    display_name: string | null;
    auto_post_enabled?: boolean;
    openai_configured?: boolean;
    tavily_configured?: boolean;
    x_connected?: boolean;
    publishing_ready?: boolean;
  }>("/settings/profile", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getXConnectUrl(accessToken?: string | null, nextPath = "/autopost") {
  return fetchJson<{ auth_url: string }>(`/settings/x/connect?next_path=${encodeURIComponent(nextPath)}`, { accessToken });
}

export function getAuthMe(accessToken: string) {
  return fetchJson<AuthMeResponse>("/auth/me", { accessToken });
}
