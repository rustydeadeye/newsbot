"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { updateCreatorSettings } from "@/lib/api";
import { ViewerRole } from "@/lib/session";
import { CreatorSettings } from "@/lib/types";

export function SettingsForm({
  settings,
  role
}: {
  settings: CreatorSettings;
  role: ViewerRole;
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
    watchlist: settings.watchlist.join(", "),
    blocked_phrases: settings.blocked_phrases.join(", "),
    timezone: settings.timezone ?? "Asia/Kolkata",
    posting_window_start: settings.posting_window_start != null ? String(settings.posting_window_start) : "",
    posting_window_end: settings.posting_window_end != null ? String(settings.posting_window_end) : "",
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
          watchlist: form.watchlist.split(",").map((item) => item.trim()).filter(Boolean),
          blocked_phrases: form.blocked_phrases.split(",").map((item) => item.trim()).filter(Boolean),
          ...(form.openai_api_key ? { openai_api_key: form.openai_api_key } : {}),
          ...(role === "admin" ? {
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

  return (
    <div className="stack">
      <label>
        <span className="field-label">Display Name</span>
        <input className="editor" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} />
      </label>
      <label>
        <span className="field-label">Tone</span>
        <input className="editor" value={form.tone} onChange={(event) => setForm({ ...form, tone: event.target.value })} />
      </label>
      <label>
        <span className="field-label">Language</span>
        <input className="editor" value={form.language} onChange={(event) => setForm({ ...form, language: event.target.value })} />
      </label>
      {role === "admin" ? (
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
      <label>
        <div className="row space">
          <span className="field-label">OpenAI API Key</span>
          <span className={settings.openai_configured ? "pill" : "pill danger"}>
            {settings.openai_configured ? "configured" : "not set"}
          </span>
        </div>
        <input
          className="editor"
          type="password"
          value={form.openai_api_key}
          onChange={(event) => setForm({ ...form, openai_api_key: event.target.value })}
          placeholder={settings.openai_configured ? "Enter a new key to replace the existing one" : "sk-..."}
          autoComplete="off"
        />
        <span className="card-subtle">Used for AI draft generation. Your key is stored securely and never exposed.</span>
      </label>
      <label>
        <span className="field-label">Watchlist (comma-separated)</span>
        <textarea className="editor" value={form.watchlist} onChange={(event) => setForm({ ...form, watchlist: event.target.value })} placeholder="e.g. RELIANCE, HDFC, SEBI" />
      </label>
      <label>
        <span className="field-label">Blocked Phrases (comma-separated)</span>
        <textarea className="editor" value={form.blocked_phrases} onChange={(event) => setForm({ ...form, blocked_phrases: event.target.value })} placeholder="e.g. rumour, unconfirmed" />
      </label>
      <div className="actions">
        <button className="button" disabled={isPending} onClick={submit}>
          {role === "admin" ? "Save Workspace Settings" : "Save My Settings"}
        </button>
      </div>
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
