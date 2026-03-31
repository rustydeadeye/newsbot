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
        if (result.warning === "x_account_not_connected") {
          setMessage("Draft approved but not queued — connect an X account in Settings first.");
        } else {
          setMessage(result.queued ? "Approved and queued." : "Approved and left unqueued.");
        }
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

  const charCount = text.length;
  const charLimit = 280;
  const charRemaining = charLimit - charCount;
  const isOverLimit = charRemaining < 0;
  const charTone = isOverLimit ? "over" : charRemaining < 20 ? "danger" : charRemaining < 50 ? "warn" : "ok";

  return (
    <div className={compact ? "stack compact-actions" : "stack"}>
      <div>
        <div className="row space">
          <span className="field-label">Draft Text</span>
          <span className={`char-count char-count-${charTone}`}>
            {charRemaining < 0 ? `${Math.abs(charRemaining)} over limit` : `${charRemaining} remaining`}
          </span>
        </div>
        <textarea className="editor" value={text} onChange={(event) => setText(event.target.value)} />
      </div>
      <div className="tweet-preview">
        <div className="field-label">Preview</div>
        <div className="tweet-preview-bubble">{text || <span className="card-subtle">Start typing to see preview…</span>}</div>
      </div>
      <label>
        <div className="row space">
          <span className="field-label">Reject Reason</span>
          <span className={`char-count ${reason.length > 200 ? "char-count-over" : "char-count-ok"}`}>
            {reason.length}/200
          </span>
        </div>
        <input className="editor" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={200} />
      </label>
      <div className="actions">
        <button className="button" disabled={isPending || isOverLimit} onClick={() => onApprove(role === "admin")}>
          {isPending ? "Approving…" : role === "admin" ? "Approve + Queue" : "Approve"}
        </button>
        {role === "admin" ? (
          <button className="button secondary" disabled={isPending || isOverLimit} onClick={() => onApprove(false)}>
            {isPending ? "Approving…" : "Approve Only"}
          </button>
        ) : null}
        <button className="button danger" disabled={isPending} onClick={onReject}>
          {isPending ? "Rejecting…" : "Reject"}
        </button>
      </div>
      {isOverLimit ? <div className="card-subtle">Shorten the text before approving ({Math.abs(charRemaining)} chars over limit).</div> : null}
      {initialStatus ? <div className="card-subtle">Current status: {initialStatus.replaceAll("_", " ")}.</div> : null}
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
