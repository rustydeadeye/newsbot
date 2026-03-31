"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { completeOnboarding, updateOnboardingOpenAI, updateOnboardingProfile } from "@/lib/api";
import { OnboardingStatus } from "@/lib/types";
import { ConnectXButton } from "@/components/connect-x-button";

type Step = "profile" | "openai" | "x" | "finish";

function parseCsv(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function OnboardingWizard({ status }: { status: OnboardingStatus }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [profile, setProfile] = useState({
    display_name: status.display_name ?? "",
    tone: status.tone,
    language: status.language,
    watchlist: status.watchlist.join(", "),
    blocked_phrases: status.blocked_phrases.join(", "),
  });
  const [openaiKey, setOpenaiKey] = useState("");

  const step: Step = useMemo(() => {
    if (!status.display_name) return "profile";
    if (!status.openai_configured) return "openai";
    if (!status.x_connected && searchParams.get("x_connected") !== "1") return "x";
    return "finish";
  }, [searchParams, status.display_name, status.openai_configured, status.x_connected]);

  function saveProfile() {
    startTransition(async () => {
      try {
        await updateOnboardingProfile({
          display_name: profile.display_name.trim(),
          tone: profile.tone,
          language: profile.language,
          watchlist: parseCsv(profile.watchlist),
          blocked_phrases: parseCsv(profile.blocked_phrases),
        });
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Failed to save profile");
      }
    });
  }

  function saveOpenAI() {
    startTransition(async () => {
      try {
        await updateOnboardingOpenAI({ openai_api_key: openaiKey.trim() });
        setOpenaiKey("");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Failed to save OpenAI key");
      }
    });
  }

  function finish() {
    startTransition(async () => {
      try {
        await completeOnboarding();
        router.push("/");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not complete onboarding");
      }
    });
  }

  return (
    <div className="panel stack">
      <div className="section-title">Customer onboarding</div>
      <div className="card-subtle">
        Complete these steps once so Newsbot can generate customer-specific drafts for your workspace.
      </div>
      <div className="workspace-list">
        <div className="workspace-list-row">
          <span>1. Profile</span>
          <strong>{status.display_name ? "Complete" : "Required"}</strong>
        </div>
        <div className="workspace-list-row">
          <span>2. OpenAI</span>
          <strong>{status.openai_configured ? "Complete" : "Required"}</strong>
        </div>
        <div className="workspace-list-row">
          <span>3. X connection</span>
          <strong>{status.x_connected ? "Connected" : "Optional for now"}</strong>
        </div>
      </div>

      {step === "profile" ? (
        <div className="stack">
          <label>
            <span className="field-label">Display name</span>
            <input className="editor" value={profile.display_name} onChange={(event) => setProfile({ ...profile, display_name: event.target.value })} />
          </label>
          <label>
            <span className="field-label">Tone</span>
            <input className="editor" value={profile.tone} onChange={(event) => setProfile({ ...profile, tone: event.target.value })} />
          </label>
          <label>
            <span className="field-label">Language</span>
            <input className="editor" value={profile.language} onChange={(event) => setProfile({ ...profile, language: event.target.value })} />
          </label>
          <label>
            <span className="field-label">Watchlist</span>
            <textarea className="editor" value={profile.watchlist} onChange={(event) => setProfile({ ...profile, watchlist: event.target.value })} />
          </label>
          <label>
            <span className="field-label">Blocked phrases</span>
            <textarea className="editor" value={profile.blocked_phrases} onChange={(event) => setProfile({ ...profile, blocked_phrases: event.target.value })} />
          </label>
          <button className="button" disabled={isPending || !profile.display_name.trim()} onClick={saveProfile} type="button">
            {isPending ? "Saving…" : "Save profile"}
          </button>
        </div>
      ) : null}

      {step === "openai" ? (
        <div className="stack">
          <label>
            <span className="field-label">OpenAI API key</span>
            <input
              className="editor"
              type="password"
              value={openaiKey}
              onChange={(event) => setOpenaiKey(event.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </label>
          <button className="button" disabled={isPending || openaiKey.trim().length < 10} onClick={saveOpenAI} type="button">
            {isPending ? "Saving…" : "Save OpenAI key"}
          </button>
        </div>
      ) : null}

      {step === "x" ? (
        <div className="stack">
          <div className="card-subtle">
            Connecting X is optional during onboarding. You can skip it for now and still generate drafts, then come back before publishing workflows are enabled.
          </div>
          <ConnectXButton connected={status.x_connected} nextPath="/onboarding" />
          <button className="button secondary" disabled={isPending} onClick={() => router.refresh()} type="button">
            Continue for now
          </button>
        </div>
      ) : null}

      {step === "finish" ? (
        <div className="stack">
          <div className="card-subtle">
            Your workspace is ready. You can generate customer-specific drafts now and connect X later if you want publishing-ready setup.
          </div>
          <button className="button" disabled={isPending} onClick={finish} type="button">
            {isPending ? "Finishing…" : "Enter workspace"}
          </button>
        </div>
      ) : null}

      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
