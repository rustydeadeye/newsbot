import { NextResponse, type NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

const PUBLIC_PATHS = new Set(["/login", "/auth/callback", "/auth/session"]);

export async function middleware(request: NextRequest) {
  const { response, isAuthenticated } = await updateSession(request);
  const path = request.nextUrl.pathname;
  const isPublicPath = PUBLIC_PATHS.has(path);

  if (!isAuthenticated && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]
};
