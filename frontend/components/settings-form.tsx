"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { TokenEditor } from "@/components/token-editor";
import { updateCreatorSettings } from "@/lib/api";
import { getAutomationStatusCopy, getDependencyMessage, getModeExplanation, getModeLabel } from "@/lib/lifecycle-ui";
import { ViewerRole } from "@/lib/session";
import { CreatorSettings } from "@/lib/types";

const TONE_OPTIONS = ["Analyst", "Clear and direct", "Measured", "Concise"];
const LANGUAGE_OPTIONS = ["English"];
const AUTOMATION_OPTIONS = [
  { value: "manual_review_only", label: "Manual" },
  { value: "auto_generate_manual_review", label: "Auto-create drafts for review (Recommended)" },
  { value: "auto_generate_auto_post_high_confidence", label: "Auto-create drafts and auto-post selected macro/regulatory items (Advanced)" },
];
type SettingsSection = "profile" | "generation" | "filters" | "automation" | "full";

export function SettingsForm({
  settings,
  role,
  section = "full",
}: {
  settings: CreatorSettings;
  role: ViewerRole;
  section?: SettingsSection;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [form, setForm] = useState({
    display_name: settings.display_name,
    tone: settings.tone,
    language: settings.language,
    max_posts_per_hour: String(settings.max_posts_per_hour),
    automation_mode: settings.automation_mode ?? "auto_generate_manual_review",
    freshness_window_hours: String(settings.freshness_window_hours ?? 12),
    watchlist: settings.watchlist,
    blocked_phrases: settings.blocked_phrases,
    timezone: settings.timezone ?? "Asia/Kolkata",
    posting_window_start: settings.posting_window_start != null ? String(settings.posting_window_start) : "",
    posting_window_end: settings.posting_window_end != null ? String(settings.posting_window_end) : "",
    auto_post_enabled: Boolean(settings.auto_post_enabled),
    auto_post_threshold: String(settings.auto_post_threshold ?? 85),
    openai_api_key: "",
  });

  function submit() {
    setFieldErrors({});
    startTransition(async () => {
      try {
        await updateCreatorSettings({
          display_name: form.display_name,
          tone: form.tone,
          language: form.language,
          max_posts_per_hour: Number(form.max_posts_per_hour),
          automation_mode: form.automation_mode,
          freshness_window_hours: Number(form.freshness_window_hours),
          watchlist: form.watchlist,
          blocked_phrases: form.blocked_phrases,
          auto_post_enabled: form.auto_post_enabled,
          auto_post_threshold: Number(form.auto_post_threshold),
          ...(form.openai_api_key ? { openai_api_key: form.openai_api_key } : {}),
          ...((role === "admin" || section === "automation" || section === "full") ? {
            timezone: form.timezone || undefined,
            posting_window_start: form.posting_window_start !== "" ? Number(form.posting_window_start) : null,
            posting_window_end: form.posting_window_end !== "" ? Number(form.posting_window_end) : null,
          } : {}),
        });
        setMessage("Settings updated.");
        router.refresh();
      } catch (error) {
        const msg = error instanceof Error ? error.message : "Update failed";
        // Try to parse FastAPI 422 field-level errors out of the error message
        try {
          const jsonStart = msg.indexOf("{");
          if (jsonStart !== -1) {
            const parsed = JSON.parse(msg.slice(jsonStart));
            if (Array.isArray(parsed?.detail)) {
              const errors: Record<string, string> = {};
              for (const item of parsed.detail) {
                const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
                if (field) errors[field] = item.msg;
              }
              if (Object.keys(errors).length > 0) {
                setFieldErrors(errors);
                return;
              }
            }
          }
        } catch {
          // not JSON — fall through to generic message
        }
        setMessage(msg);
      }
    });
  }

  const showProfile = section === "profile" || section === "full";
  const showGeneration = section === "generation" || section === "full";
  const showFilters = section === "filters" || section === "full";
  const showAutomation = section === "automation" || section === "full";
  const showAdminFields = role === "admin" && section === "full";
  const showAutoPostControls = form.automation_mode === "auto_generate_auto_post_high_confidence";
  const automationPreview = {
    ...settings,
    automation_mode: form.automation_mode,
    freshness_window_hours: Number(form.freshness_window_hours),
    timezone: form.timezone || settings.timezone,
    auto_post_enabled: form.auto_post_enabled,
    auto_post_threshold: Number(form.auto_post_threshold),
  };
  const dependencyMessage = getDependencyMessage({
    ...automationPreview,
  });

  return (
    <div className="stack">
      {showProfile ? (
        <>
          <label>
            <span className="field-label">Display Name</span>
            <input className="editor compact" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} />
          </label>
          <label>
            <span className="field-label">Tone</span>
            <select className="editor compact-select" value={form.tone} onChange={(event) => setForm({ ...form, tone: event.target.value })}>
              {TONE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="field-label">Language</span>
            <select className="editor compact-select" value={form.language} onChange={(event) => setForm({ ...form, language: event.target.value })}>
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : null}
      {showAdminFields ? (
        <>
          <label>
            <span className="field-label">Max Posts Per Hour</span>
            <input className="editor" value={form.max_posts_per_hour} onChange={(event) => setForm({ ...form, max_posts_per_hour: event.target.value })} />
          </label>
          <label>
            <span className="field-label">Timezone</span>
            <input className="editor" value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} placeholder="e.g. Asia/Kolkata" />
            {fieldErrors.timezone
              ? <span className="card-subtle" style={{ color: "var(--danger, #c00)" }}>{fieldErrors.timezone}</span>
              : <span className="card-subtle">Invalid values default to Asia/Kolkata.</span>}
          </label>
          <label>
            <span className="field-label">Posting Window Start (hour 0–23, leave blank for no restriction)</span>
            <input className="editor" type="number" min={0} max={23} value={form.posting_window_start} onChange={(event) => setForm({ ...form, posting_window_start: event.target.value })} placeholder="e.g. 9" />
          </label>
          <label>
            <span className="field-label">Posting Window End (hour 0–23)</span>
            <input className="editor" type="number" min={0} max={23} value={form.posting_window_end} onChange={(event) => setForm({ ...form, posting_window_end: event.target.value })} placeholder="e.g. 22" />
          </label>
        </>
      ) : null}
      {showGeneration ? (
        <label>
          <div className="row space">
            <span className="field-label">OpenAI API Key</span>
            <span className={settings.openai_configured ? "pill" : "pill danger"}>
              {settings.openai_configured ? "configured" : "not set"}
            </span>
          </div>
          <input
            className="editor compact"
            type="password"
            value={form.openai_api_key}
            onChange={(event) => setForm({ ...form, openai_api_key: event.target.value })}
            placeholder={settings.openai_configured ? "Enter a new key to replace the existing one" : "sk-..."}
            autoComplete="off"
          />
          <span className="card-subtle">Used only for draft generation in your workspace. Your key stays hidden after save.</span>
        </label>
      ) : null}
      {showAutomation ? (
        <>
          <div className="settings-group">
            <div className="section-label">How Newsbot works while you are away</div>
            <label>
              <span className="field-label">Automation preset</span>
              <select className="editor compact-select" value={form.automation_mode} onChange={(event) => setForm({ ...form, automation_mode: event.target.value })}>
                {AUTOMATION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="card-subtle"><strong>{getModeLabel(form.automation_mode)}</strong> — {getModeExplanation({ ...settings, automation_mode: form.automation_mode })}</div>
            <div className="settings-inline-note">{getAutomationStatusCopy(automationPreview)}</div>
            {dependencyMessage ? <div className="settings-inline-note">{dependencyMessage}</div> : null}
          </div>
          <details className="settings-disclosure">
            <summary>Advanced timing and freshness</summary>
            <div className="settings-group">
              <div className="section-label">When posts are allowed</div>
              <label>
                <span className="field-label">Freshness window (hours)</span>
                <input className="editor compact" type="number" min={1} max={72} value={form.freshness_window_hours} onChange={(event) => setForm({ ...form, freshness_window_hours: event.target.value })} />
              </label>
              <label>
                <span className="field-label">Timezone</span>
                <input className="editor compact" value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} placeholder="Asia/Kolkata" />
                <span className="card-subtle">Use your primary posting timezone. Invalid values fall back to Asia/Kolkata.</span>
              </label>
              <label>
                <span className="field-label">Posting window start</span>
                <input className="editor compact" type="number" min={0} max={23} value={form.posting_window_start} onChange={(event) => setForm({ ...form, posting_window_start: event.target.value })} placeholder="e.g. 9" />
              </label>
              <label>
                <span className="field-label">Posting window end</span>
                <input className="editor compact" type="number" min={0} max={23} value={form.posting_window_end} onChange={(event) => setForm({ ...form, posting_window_end: event.target.value })} placeholder="e.g. 21" />
                <span className="card-subtle">Leave both posting-window fields blank if you do not want time restrictions.</span>
              </label>
            </div>
          </details>
          {showAutoPostControls ? (
            <div className="settings-group">
              <div className="section-label">Auto-post safety</div>
              <div className="settings-inline-note">
                Auto-post stays off by default and only applies to selected macro and regulatory items in this version.
              </div>
              <label className="workspace-list-row">
                <span>Allow auto-post</span>
                <input
                  type="checkbox"
                  checked={form.auto_post_enabled}
                  disabled={!settings.x_connected || !settings.openai_configured}
                  onChange={(event) => setForm({ ...form, auto_post_enabled: event.target.checked })}
                />
              </label>
              <label>
                <span className="field-label">Auto-post threshold</span>
                <input
                  className="editor compact"
                  type="number"
                  min={50}
                  max={100}
                  value={form.auto_post_threshold}
                  disabled={!settings.x_connected || !settings.openai_configured}
                  onChange={(event) => setForm({ ...form, auto_post_threshold: event.target.value })}
                />
                <span className="card-subtle">Higher thresholds keep auto-posting more conservative.</span>
              </label>
            </div>
          ) : null}
        </>
      ) : null}
      {showFilters ? (
        <>
          <TokenEditor
            label="Watchlist"
            value={form.watchlist}
            onChange={(watchlist) => setForm({ ...form, watchlist })}
            placeholder="Add companies, tickers, or topics"
            help="Newsbot uses this to prioritize the updates you care about most."
          />
          <TokenEditor
            label="Blocked phrases"
            value={form.blocked_phrases}
            onChange={(blocked_phrases) => setForm({ ...form, blocked_phrases })}
            placeholder="Add phrases to avoid in draft copy"
            help="Use this to keep unwanted wording out of generated drafts."
          />
        </>
      ) : null}
      <div className="actions">
        <button className="button" disabled={isPending} onClick={submit}>
          {role === "admin" ? "Save Workspace Settings" : "Save Section"}
        </button>
      </div>
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
