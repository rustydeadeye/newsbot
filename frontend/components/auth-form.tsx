"use client";

import { useState, useTransition } from "react";

import { getAuthMe } from "@/lib/api";
import { getRoleHomePath } from "@/lib/product-mode";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

async function waitForSession() {
  const supabase = getSupabaseBrowserClient();
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const {
      data: { session }
    } = await supabase.auth.getSession();
    if (session?.access_token) {
      return session;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 150));
  }
  return null;
}

async function syncServerSession(accessToken: string, refreshToken: string) {
  const response = await fetch("/auth/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      access_token: accessToken,
      refresh_token: refreshToken,
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Failed to sync session: ${detail}`);
  }
}

export function AuthForm() {
  const [isPending, startTransition] = useTransition();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function submit() {
    startTransition(async () => {
      try {
        const supabase = getSupabaseBrowserClient();
        if (mode === "signin") {
          const { error } = await supabase.auth.signInWithPassword({ email, password });
          if (error) {
            throw error;
          }
          const session = await waitForSession();
          if (!session?.access_token || !session.refresh_token) {
            throw new Error("Signed in, but the session could not be restored.");
          }
          await syncServerSession(session.access_token, session.refresh_token);
          const auth = await getAuthMe(session.access_token);
          window.location.assign(getRoleHomePath(auth.viewer.role));
          return;
        }

        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/auth/callback`
          }
        });
        if (error) {
          throw error;
        }
        setMessage("Account created. Check your email if confirmation is enabled, then sign in.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Authentication failed");
      }
    });
  }

  return (
    <div className="stack">
      <div className="role-switcher-buttons">
        <button
          className={mode === "signin" ? "button switch active" : "button switch secondary"}
          disabled={isPending}
          onClick={() => setMode("signin")}
          type="button"
        >
          Sign In
        </button>
        <button
          className={mode === "signup" ? "button switch active" : "button switch secondary"}
          disabled={isPending}
          onClick={() => setMode("signup")}
          type="button"
        >
          Create Account
        </button>
      </div>
      <label htmlFor="auth-email">
        <span className="field-label">Email</span>
        <input
          id="auth-email"
          className="editor compact"
          type="email"
          autoComplete="email"
          maxLength={254}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <label htmlFor="auth-password">
        <span className="field-label">Password</span>
        <input
          id="auth-password"
          className="editor compact"
          type="password"
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <button className="button" disabled={isPending} onClick={submit} type="button">
        {mode === "signin" ? "Sign In" : "Create Account"}
      </button>
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
