import { redirect } from "next/navigation";

import { getAuthMe, getOnboardingStatus } from "@/lib/api";
import { ViewerProfile } from "@/lib/session";
import { OnboardingStatus } from "@/lib/types";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function getServerViewer(): Promise<{ viewer: ViewerProfile; accessToken: string } | null> {
  const supabase = await createSupabaseServerClient();

  // getSession() reads from cookie storage — single call avoids
  // the race where getUser() refreshes the token but the cookie
  // hasn't been flushed before getSession() reads the old value.
  const {
    data: { session }
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    return null;
  }

  // Validate the token is still accepted by the backend.
  // If it fails (expired, backend misconfiguration), treat as logged-out
  // rather than crashing the page.
  try {
    const payload = await getAuthMe(session.access_token);
    return { viewer: payload.viewer, accessToken: session.access_token };
  } catch {
    return null;
  }
}

export async function requireServerViewer(): Promise<{ viewer: ViewerProfile; accessToken: string }> {
  const viewer = await getServerViewer();
  if (!viewer) {
    redirect("/login");
  }
  return viewer;
}

export async function requireWorkspaceSession(): Promise<{
  viewer: ViewerProfile;
  accessToken: string;
  onboarding: OnboardingStatus | null;
}> {
  const auth = await requireServerViewer();
  if (!auth.viewer.role || auth.viewer.role !== "customer") {
    return { ...auth, onboarding: null };
  }
  const onboarding = await getOnboardingStatus(auth.accessToken);
  return { ...auth, onboarding };
}
