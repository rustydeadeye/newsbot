"use client";

import { useState, useTransition } from "react";

import { runPipeline } from "@/lib/api";

export function PipelineRunButton() {
  const [result, setResult] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function run() {
    setResult(null);
    startTransition(async () => {
      try {
        const counts = await runPipeline();
        const ingested = typeof counts.ingested === "object"
          ? Object.values(counts.ingested as Record<string, number>).reduce((a, b) => a + b, 0)
          : counts.ingested;
        setResult(`Cycle complete: ${ingested} ingested, ${counts.normalized} normalized, ${counts.drafted} drafted, ${counts.posted} posted`);
      } catch (error) {
        setResult(error instanceof Error ? error.message : "Pipeline run failed");
      }
    });
  }

  return (
    <div className="row">
      <button className="button secondary" disabled={isPending} onClick={run}>
        {isPending ? "Running…" : "Run Pipeline Now"}
      </button>
      {result ? <span className="card-subtle">{result}</span> : null}
    </div>
  );
}
