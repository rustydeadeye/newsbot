"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { generateDrafts } from "@/lib/api";

export function GenerateDraftsButton({ label = "Generate drafts now" }: { label?: string }) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function start() {
    startTransition(async () => {
      try {
        const run = await generateDrafts();
        if (run.status === "queued" || run.status === "running") {
          setMessage("Draft generation started. This page will update as soon as your queue is ready.");
        } else {
          setMessage(`Latest generation status: ${run.status.replaceAll("_", " ")}.`);
        }
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Failed to start generation");
      }
    });
  }

  return (
    <div className="stack">
      <button className="button" disabled={isPending} onClick={start} type="button">
        {isPending ? "Starting…" : label}
      </button>
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
