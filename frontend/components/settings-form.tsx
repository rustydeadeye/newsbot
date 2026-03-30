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
  const [form, setForm] = useState({
    display_name: settings.display_name,
    tone: settings.tone,
    language: settings.language,
    max_posts_per_hour: String(settings.max_posts_per_hour),
    watchlist: settings.watchlist.join(", "),
    blocked_phrases: settings.blocked_phrases.join(", ")
  });

  function submit() {
    startTransition(async () => {
      try {
        await updateCreatorSettings({
          display_name: form.display_name,
          tone: form.tone,
          language: form.language,
          max_posts_per_hour: Number(form.max_posts_per_hour),
          watchlist: form.watchlist.split(",").map((item) => item.trim()).filter(Boolean),
          blocked_phrases: form.blocked_phrases.split(",").map((item) => item.trim()).filter(Boolean)
        });
        setMessage("Settings updated.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Update failed");
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
        <label>
          <span className="field-label">Max Posts Per Hour</span>
          <input className="editor" value={form.max_posts_per_hour} onChange={(event) => setForm({ ...form, max_posts_per_hour: event.target.value })} />
        </label>
      ) : null}
      <label>
        <span className="field-label">Watchlist</span>
        <textarea className="editor" value={form.watchlist} onChange={(event) => setForm({ ...form, watchlist: event.target.value })} />
      </label>
      <label>
        <span className="field-label">Blocked Phrases</span>
        <textarea className="editor" value={form.blocked_phrases} onChange={(event) => setForm({ ...form, blocked_phrases: event.target.value })} />
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
