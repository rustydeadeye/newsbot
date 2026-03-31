"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { reopenDraft } from "@/lib/api";
import { DraftSummary } from "@/lib/types";

export function RejectedDraftsSection({ drafts: initialDrafts }: { drafts: DraftSummary[] }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const [drafts, setDrafts] = useState(initialDrafts);
  const [reopenErrors, setReopenErrors] = useState<Record<number, string>>({});
  const [isPending, startTransition] = useTransition();

  function onReopen(draftId: number) {
    startTransition(async () => {
      try {
        await reopenDraft(draftId);
        setDrafts((prev) => prev.filter((d) => d.id !== draftId));
        router.refresh();
      } catch (error) {
        setReopenErrors((prev) => ({
          ...prev,
          [draftId]: error instanceof Error ? error.message : "Re-open failed"
        }));
      }
    });
  }

  if (drafts.length === 0) return null;

  return (
    <div className="panel">
      <button
        className="row space"
        style={{ background: "none", border: "none", cursor: "pointer", width: "100%", textAlign: "left", padding: 0 }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="section-title">Rejected ({drafts.length})</div>
        <span className="card-subtle">{expanded ? "Hide" : "Show"}</span>
      </button>
      {expanded ? (
        <div className="stack" style={{ marginTop: "0.75rem" }}>
          {drafts.map((draft) => {
            const rejectedBy = String(draft.safety_flags?.rejected_by ?? "—");
            const reason = String(draft.safety_flags?.rejection_reason ?? "No reason recorded");
            return (
              <div key={draft.id} className="publish-row">
                <div className="row space">
                  <span className="pill danger">rejected</span>
                  <span className="mono">{draft.event?.ticker ?? "MARKET"}</span>
                </div>
                <div className="queue-row-title">{draft.draft_text}</div>
                <div className="card-subtle">Reason: {reason}</div>
                <div className="card-subtle">Rejected by: {rejectedBy}</div>
                {reopenErrors[draft.id] ? <div className="card-subtle">{reopenErrors[draft.id]}</div> : null}
                <div className="actions">
                  <button className="button secondary" disabled={isPending} onClick={() => onReopen(draft.id)}>
                    {isPending ? "Re-opening…" : "Re-open"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
