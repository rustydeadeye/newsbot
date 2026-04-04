"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { ConnectXButton } from "@/components/connect-x-button";
import { updateProfileSettings } from "@/lib/api";

export function AutopostSetupPanel({
  displayName,
  xConnected,
}: {
  displayName: string | null;
  xConnected: boolean;
}) {
  const router = useRouter();
  const [name, setName] = useState(displayName ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function saveName() {
    setMessage(null);
    startTransition(async () => {
      try {
        await updateProfileSettings({ display_name: name.trim() });
        setMessage("Name saved.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not save your name");
      }
    });
  }

  return (
    <div className="panel stack">
      <div className="eyebrow">Simple setup</div>
      <div className="section-hero-title">Get autoposting ready</div>
      <p className="card-subtle">
        This branch keeps setup intentionally small. Add your name, connect X, and then you can start autoposting.
      </p>
      <label>
        <span className="field-label">Display name</span>
        <input
          className="editor compact"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="How should Newsbot refer to you?"
        />
      </label>
      <div className="actions">
        <button className="button" disabled={isPending || !name.trim()} onClick={saveName} type="button">
          {isPending ? "Saving…" : "Save name"}
        </button>
      </div>
      <ConnectXButton connected={xConnected} nextPath="/autopost" />
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
