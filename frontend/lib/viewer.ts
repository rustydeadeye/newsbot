import { redirect } from "next/navigation";
import { cache } from "react";

import { getAuthMe, getOnboardingStatus } from "@/lib/api";
import { ViewerProfile } from "@/lib/session";
import { OnboardingStatus } from "@/lib/types";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const readServerViewer = cache(async (): Promise<{ viewer: ViewerProfile; accessToken: string } | null> => {
  try {
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
    // If it fails (expired, backend misconfiguration, transient SSR fetch issue),
    // treat as logged-out rather than crashing the entire render tree.
    const payload = await getAuthMe(session.access_token);
    return { viewer: payload.viewer, accessToken: session.access_token };
  } catch {
    return null;
  }
});

export async function getServerViewer(): Promise<{ viewer: ViewerProfile; accessToken: string } | null> {
  return readServerViewer();
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
  onboardingError: string | null;
}> {
  const auth = await requireServerViewer();
  if (!auth.viewer.role || auth.viewer.role !== "customer") {
    return { ...auth, onboarding: null, onboardingError: null };
  }
  try {
    const onboarding = await getOnboardingStatus(auth.accessToken);
    return { ...auth, onboarding, onboardingError: null };
  } catch (error) {
    return {
      ...auth,
      onboarding: null,
      onboardingError: error instanceof Error ? error.message : "Failed to load onboarding state",
    };
  }
}
