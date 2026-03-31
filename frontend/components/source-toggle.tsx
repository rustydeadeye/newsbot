"use client";

import { useState, useTransition } from "react";

import { patchSource } from "@/lib/api";
import { SourceSummary } from "@/lib/types";

export function SourceToggle({ source: initialSource }: { source: SourceSummary }) {
  const [source, setSource] = useState(initialSource);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function toggle() {
    startTransition(async () => {
      try {
        const updated = await patchSource(source.id, { enabled: !source.enabled });
        setSource((prev) => ({ ...prev, enabled: updated.enabled }));
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Update failed");
      }
    });
  }

  return (
    <div className="row space source-row">
      <div>
        <div>{source.name}</div>
        <div className="card-subtle">
          {source.type} | poll {source.poll_interval_sec}s
        </div>
        {error ? <div className="card-subtle">{error}</div> : null}
      </div>
      <div className="row">
        <span className={source.enabled ? "pill" : "pill danger"}>{source.enabled ? "enabled" : "disabled"}</span>
        <button className="button secondary" disabled={isPending} onClick={toggle}>
          {isPending ? "Saving…" : source.enabled ? "Disable" : "Enable"}
        </button>
      </div>
    </div>
  );
}
