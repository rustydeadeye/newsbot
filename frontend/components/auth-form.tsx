"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

export function AuthForm() {
  const router = useRouter();
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
          router.push("/");
          router.refresh();
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
      <label>
        <span className="field-label">Email</span>
        <input className="editor compact" value={email} onChange={(event) => setEmail(event.target.value)} />
      </label>
      <label>
        <span className="field-label">Password</span>
        <input className="editor compact" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      <button className="button" disabled={isPending} onClick={submit} type="button">
        {mode === "signin" ? "Sign In" : "Create Account"}
      </button>
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
