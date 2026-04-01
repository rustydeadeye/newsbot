import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !publishableKey) {
    return NextResponse.json({ error: "Supabase frontend auth is not configured" }, { status: 500 });
  }

  const { access_token: accessToken, refresh_token: refreshToken } = (await request.json()) as {
    access_token?: string;
    refresh_token?: string;
  };

  if (!accessToken || !refreshToken) {
    return NextResponse.json({ error: "Missing session tokens" }, { status: 400 });
  }

  let response = NextResponse.json({ ok: true });
  const supabase = createServerClient(url, publishableKey, {
    cookies: {
      getAll() {
        return request.headers
          .get("cookie")
          ?.split(";")
          .map((value) => value.trim())
          .filter(Boolean)
          .map((value) => {
            const separator = value.indexOf("=");
            if (separator === -1) {
              return { name: value, value: "" };
            }
            return { name: value.slice(0, separator), value: value.slice(separator + 1) };
          }) ?? [];
      },
      setAll(cookiesToSet) {
        response = NextResponse.json({ ok: true });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      }
    }
  });

  const { error } = await supabase.auth.setSession({
    access_token: accessToken,
    refresh_token: refreshToken,
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 400 });
  }

  return response;
}
