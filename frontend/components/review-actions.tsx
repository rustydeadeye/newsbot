"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { approveDraft, rejectDraft } from "@/lib/api";
import { ViewerRole } from "@/lib/session";

export function ReviewActions({
  draftId,
  initialText,
  role,
  initialStatus,
  compact = false
}: {
  draftId: number;
  initialText: string;
  role: ViewerRole;
  initialStatus?: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const [text, setText] = useState(initialText);
  const [reason, setReason] = useState("Needs rewrite");
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function onApprove(autoQueue: boolean) {
    startTransition(async () => {
      try {
        const result = await approveDraft(draftId, {
          edited_text: text,
          auto_queue: autoQueue
        });
        setMessage(result.queued ? "Approved and queued." : "Approved and left unqueued.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Approve failed");
      }
    });
  }

  function onReject() {
    startTransition(async () => {
      try {
        await rejectDraft(draftId, { reason });
        setMessage("Draft rejected.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Reject failed");
      }
    });
  }

  return (
    <div className={compact ? "stack compact-actions" : "stack"}>
      <label>
        <span className="field-label">Draft Text</span>
        <textarea className="editor" value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <label>
        <span className="field-label">Reject Reason</span>
        <input className="editor" value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="actions">
        <button className="button" disabled={isPending} onClick={() => onApprove(role === "admin")}>
          {role === "admin" ? "Approve + Queue" : "Approve"}
        </button>
        {role === "admin" ? (
          <button className="button secondary" disabled={isPending} onClick={() => onApprove(false)}>
            Approve Only
          </button>
        ) : null}
        <button className="button danger" disabled={isPending} onClick={onReject}>
          Reject
        </button>
      </div>
      {initialStatus ? <div className="card-subtle">Current status: {initialStatus.replaceAll("_", " ")}.</div> : null}
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
