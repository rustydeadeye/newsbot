import { NextResponse, type NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

const PUBLIC_PATHS = new Set(["/login", "/auth/callback", "/auth/session"]);
const LEGACY_REDIRECT_PATHS = new Set(["/drafts", "/events", "/jobs", "/settings"]);
const FRIENDLY_REDIRECTS = new Map([
  ["/autopost", "/dashboard"],
  ["/wire", "/operations"],
]);

export async function middleware(request: NextRequest) {
  const { response, isAuthenticated } = await updateSession(request);
  const path = request.nextUrl.pathname;
  const isPublicPath = PUBLIC_PATHS.has(path);

  if (!isAuthenticated && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  if (isAuthenticated && FRIENDLY_REDIRECTS.has(path)) {
    return NextResponse.redirect(new URL(FRIENDLY_REDIRECTS.get(path) ?? "/", request.url));
  }

  if (isAuthenticated && LEGACY_REDIRECT_PATHS.has(path)) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]
};
