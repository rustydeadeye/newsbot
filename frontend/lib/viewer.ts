import { redirect } from "next/navigation";

import { getAuthMe } from "@/lib/api";
import { ViewerProfile } from "@/lib/session";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function getServerViewer(): Promise<{ viewer: ViewerProfile; accessToken: string } | null> {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();
  if (!user) {
    return null;
  }

  const {
    data: { session }
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return null;
  }

  const payload = await getAuthMe(session.access_token);
  return { viewer: payload.viewer, accessToken: session.access_token };
}

export async function requireServerViewer(): Promise<{ viewer: ViewerProfile; accessToken: string }> {
  const viewer = await getServerViewer();
  if (!viewer) {
    redirect("/login");
  }
  return viewer;
}
