"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { completeOnboarding, updateOnboardingOpenAI, updateOnboardingProfile } from "@/lib/api";
import { OnboardingStatus } from "@/lib/types";
import { ConnectXButton } from "@/components/connect-x-button";
import { TokenEditor } from "@/components/token-editor";

type Step = "profile" | "openai" | "x" | "finish";
const TONE_OPTIONS = ["Analyst", "Clear and direct", "Measured", "Concise"];
const LANGUAGE_OPTIONS = ["English"];

const STEP_CONTENT: Record<Exclude<Step, "finish">, { number: string; title: string; description: string }> = {
  profile: {
    number: "Step 1",
    title: "Set your profile and voice",
    description: "Tell Newsbot how to present your workspace and which updates should matter most.",
  },
  openai: {
    number: "Step 2",
    title: "Unlock draft generation",
    description: "Add your OpenAI key so Newsbot can create draft copy for your workspace.",
  },
  x: {
    number: "Optional step",
    title: "Connect X when you are ready",
    description: "You can skip this for now and come back later before publishing workflows are enabled.",
  },
};

export function OnboardingWizard({ status }: { status: OnboardingStatus }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [skipXForNow, setSkipXForNow] = useState(false);
  const [profile, setProfile] = useState({
    display_name: status.display_name ?? "",
    tone: status.tone,
    language: status.language,
    watchlist: status.watchlist,
    blocked_phrases: status.blocked_phrases,
  });
  const [openaiKey, setOpenaiKey] = useState("");

  const step: Step = useMemo(() => {
    if (!status.display_name) return "profile";
    if (!status.openai_configured) return "openai";
    if (!status.x_connected && searchParams.get("x_connected") !== "1" && !skipXForNow) return "x";
    return "finish";
  }, [searchParams, skipXForNow, status.display_name, status.openai_configured, status.x_connected]);

  function saveProfile() {
    setMessage(null);
    startTransition(async () => {
      try {
        await updateOnboardingProfile({
          display_name: profile.display_name.trim(),
          tone: profile.tone,
          language: profile.language,
          watchlist: profile.watchlist,
          blocked_phrases: profile.blocked_phrases,
        });
        setMessage("Profile saved. You can move to the next step.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Failed to save profile");
      }
    });
  }

  function saveOpenAI() {
    setMessage(null);
    startTransition(async () => {
      try {
        await updateOnboardingOpenAI({ openai_api_key: openaiKey.trim() });
        setOpenaiKey("");
        setMessage("OpenAI key saved. Draft generation is now unlocked.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Failed to save OpenAI key");
      }
    });
  }

  function finish() {
    setMessage(null);
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

  const progressItems = [
    {
      key: "profile",
      label: "Profile",
      detail: status.display_name ? "Complete" : "Required",
      state: status.display_name ? "done" : step === "profile" ? "current" : "upcoming",
    },
    {
      key: "openai",
      label: "OpenAI",
      detail: status.openai_configured ? "Complete" : "Required",
      state: status.openai_configured ? "done" : step === "openai" ? "current" : "upcoming",
    },
    {
      key: "x",
      label: "X connection",
      detail: status.x_connected ? "Connected" : "Optional",
      state: status.x_connected ? "done" : step === "x" ? "current" : step === "finish" ? "upcoming" : "upcoming",
    },
  ] as const;

  const activeStepMeta = step === "finish" ? null : STEP_CONTENT[step];

  return (
    <div className="panel onboarding-wizard">
      <div className="onboarding-progress">
        <div className="section-title">Setup progress</div>
        <div className="onboarding-progress-list">
          {progressItems.map((item) => (
            <div key={item.key} className={`onboarding-progress-item onboarding-progress-item-${item.state}`}>
              <div>
                <div className="field-label">{item.label}</div>
                <div className="card-subtle">{item.detail}</div>
              </div>
              <span className={item.state === "done" ? "pill" : item.state === "current" ? "pill warn" : "pill subtle"}>
                {item.state === "done" ? "Done" : item.state === "current" ? "Current" : "Next"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {activeStepMeta ? (
        <div className="onboarding-step-hero">
          <div className="eyebrow">{activeStepMeta.number}</div>
          <div className="section-hero-title">{activeStepMeta.title}</div>
          <p className="card-subtle">{activeStepMeta.description}</p>
        </div>
      ) : null}

      {step === "profile" ? (
        <div className="stack onboarding-step-card">
          <label>
            <span className="field-label">Display name</span>
            <input className="editor compact" value={profile.display_name} onChange={(event) => setProfile({ ...profile, display_name: event.target.value })} placeholder="How should Newsbot refer to you?" />
          </label>
          <label>
            <span className="field-label">Tone</span>
            <select className="editor compact-select" value={profile.tone} onChange={(event) => setProfile({ ...profile, tone: event.target.value })}>
              {TONE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Language</span>
            <select className="editor compact-select" value={profile.language} onChange={(event) => setProfile({ ...profile, language: event.target.value })}>
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <TokenEditor
            label="Watchlist"
            value={profile.watchlist}
            onChange={(watchlist) => setProfile({ ...profile, watchlist })}
            placeholder="Add companies, tickers, or topics"
            help="Examples: RBI, HDFC Bank, mutual funds, SEBI."
          />
          <TokenEditor
            label="Blocked phrases"
            value={profile.blocked_phrases}
            onChange={(blocked_phrases) => setProfile({ ...profile, blocked_phrases })}
            placeholder="Add terms you do not want in drafts"
            help="Examples: unconfirmed, rumor, guaranteed."
          />
          <button className="button onboarding-primary-cta" disabled={isPending || !profile.display_name.trim()} onClick={saveProfile} type="button">
            {isPending ? "Saving…" : "Save and continue"}
          </button>
        </div>
      ) : null}

      {step === "openai" ? (
        <div className="stack onboarding-step-card">
          <div className="card-subtle">
            Your OpenAI key unlocks draft generation for this workspace. Newsbot uses it to prepare suggestions for review, and it stays stored securely.
          </div>
          <label>
            <span className="field-label">OpenAI API key</span>
            <input
              className="editor compact"
              type="password"
              value={openaiKey}
              onChange={(event) => setOpenaiKey(event.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </label>
          <button className="button onboarding-primary-cta" disabled={isPending || openaiKey.trim().length < 10} onClick={saveOpenAI} type="button">
            {isPending ? "Saving…" : "Save and continue"}
          </button>
        </div>
      ) : null}

      {step === "x" ? (
        <div className="stack onboarding-step-card">
          <div className="card-subtle">
            You can skip this for now, generate your first drafts, and come back later when you are ready to connect a publishing account.
          </div>
          <ConnectXButton connected={status.x_connected} nextPath="/onboarding" />
          <button
            className="button secondary onboarding-primary-cta"
            disabled={isPending}
            onClick={() => {
              setSkipXForNow(true);
              setMessage("You can connect X later from Settings when you are ready.");
            }}
            type="button"
          >
            Continue for now
          </button>
        </div>
      ) : null}

      {step === "finish" ? (
        <div className="stack onboarding-step-card">
          <div className="eyebrow">Setup complete</div>
          <div className="section-hero-title">Your workspace is ready</div>
          <div className="card-subtle">
            You will land on Home next, where you can generate your first drafts immediately. X can be connected later whenever you want to prepare for publishing.
          </div>
          <button className="button onboarding-primary-cta" disabled={isPending} onClick={finish} type="button">
            {isPending ? "Finishing…" : "Enter workspace"}
          </button>
        </div>
      ) : null}

      {message ? <div className="card-subtle onboarding-message">{message}</div> : null}
    </div>
  );
}
