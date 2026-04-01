"use client";

import { useState, useTransition } from "react";

import { approveDraft, rejectDraft } from "@/lib/api";
import { formatPublishTime, getRecommendedPublishPlan, toIsoString } from "@/lib/publish-plan";
import { ViewerRole } from "@/lib/session";
import { CreatorSettings } from "@/lib/types";

export function ReviewActions({
  draftId,
  initialText,
  role,
  initialStatus,
  compact = false,
  canPublish = false,
  publishSettings = null,
}: {
  draftId: number;
  initialText: string;
  role: ViewerRole;
  initialStatus?: string;
  compact?: boolean;
  canPublish?: boolean;
  publishSettings?: CreatorSettings | null;
}) {
  const [text, setText] = useState(initialText);
  const [reason, setReason] = useState("Needs rewrite");
  const [message, setMessage] = useState<string | null>(null);
  const [scheduleLater, setScheduleLater] = useState(false);
  const [scheduledFor, setScheduledFor] = useState("");
  const [lastAction, setLastAction] = useState<"approved" | "rejected" | null>(null);
  const [resolvedStatus, setResolvedStatus] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const recommendedPlan = getRecommendedPublishPlan(publishSettings);

  function onApprove(autoQueue: boolean) {
    startTransition(async () => {
      try {
        if (autoQueue && scheduleLater && scheduledFor) {
          const selectedDateIso = toIsoString(scheduledFor);
          if (!selectedDateIso || new Date(selectedDateIso).getTime() <= Date.now()) {
            setMessage("Choose a future time for scheduled posting.");
            return;
          }
        }
        const scheduledAt = autoQueue
          ? scheduleLater && scheduledFor
            ? toIsoString(scheduledFor)
            : recommendedPlan?.mode === "scheduled"
              ? recommendedPlan.scheduledFor
              : null
          : null;
        const result = await approveDraft(draftId, {
          edited_text: text,
          auto_queue: autoQueue,
          scheduled_for: scheduledAt,
        });
        if (result.warning === "x_account_not_connected") {
          setMessage("Draft approved. Connect your X account in Settings when you are ready to schedule publishing.");
        } else if (result.draft.status === "posted") {
          setMessage("Approved and posted to X.");
        } else if (result.draft.status === "publishing") {
          setMessage("Approved and sent to publishing. Newsbot is posting it now.");
        } else if (result.publish_job?.scheduled_for) {
          setMessage(`Approved and scheduled for ${formatPublishTime(result.publish_job.scheduled_for, publishSettings?.timezone ?? "Asia/Kolkata")}.`);
        } else {
          setMessage(result.queued ? "Approved and queued for immediate publishing." : "Approved and left unqueued.");
        }
        setLastAction("approved");
        setResolvedStatus(result.draft.status);
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
        setLastAction("rejected");
        setResolvedStatus("rejected");
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
  const isResolved = lastAction !== null;
  const minimumScheduleValue = new Date(Date.now() + 60_000).toISOString().slice(0, 16);

  if (isResolved) {
    return (
      <div className={compact ? "stack compact-actions" : "stack"}>
        <div className="publish-plan-card">
          <div className="section-label">{lastAction === "approved" ? "Draft moved forward" : "Draft removed from review"}</div>
          <div className="publish-plan-title">
            {lastAction === "approved"
              ? resolvedStatus === "posted"
                ? "Posted successfully"
                : resolvedStatus === "publishing"
                  ? "Publishing now"
                  : resolvedStatus === "queued"
                    ? "Queued for publishing"
                    : "Saved as approved"
              : "Rejected and removed from the live queue"}
          </div>
          <div className="card-subtle">
            {message ??
              (lastAction === "approved"
                ? "This draft has moved out of the live review queue. Refresh the workspace when you want to load the next state."
                : "This draft has been removed from the live review queue. Refresh the workspace when you want to load the next state.")}
          </div>
        </div>
      </div>
    );
  }

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
      {role === "customer" && canPublish && recommendedPlan ? (
        <div className="publish-plan-card">
          <div className="section-label">Recommended timing</div>
          <div className="publish-plan-title">{recommendedPlan.summary}</div>
          <div className="card-subtle">{recommendedPlan.helper}</div>
          <div className="card-subtle">Timezone: {recommendedPlan.timezone}</div>
        </div>
      ) : null}
      <div className="actions">
        <button className="button" disabled={isPending || isOverLimit} onClick={() => onApprove(role === "admin" || canPublish)}>
          {isPending
            ? "Approving…"
            : role === "admin"
              ? "Approve + Queue"
              : canPublish
                ? recommendedPlan?.mode === "now"
                  ? "Approve & Post Now"
                  : "Approve & Schedule"
                : "Approve only"}
        </button>
        {role === "admin" ? (
          <button className="button secondary" disabled={isPending || isOverLimit} onClick={() => onApprove(false)}>
            {isPending ? "Approving…" : "Approve Only"}
          </button>
        ) : canPublish ? (
          <>
            <button className="button secondary" disabled={isPending || isOverLimit} onClick={() => onApprove(false)}>
              {isPending ? "Approving…" : "Save as approved"}
            </button>
            <button className="button secondary" disabled={isPending || isOverLimit} onClick={() => setScheduleLater((value) => !value)}>
              {scheduleLater ? "Use recommended timing" : "Choose time"}
            </button>
          </>
        ) : null}
        <button className="button danger" disabled={isPending} onClick={onReject}>
          {isPending ? "Rejecting…" : "Reject"}
        </button>
      </div>
      {role === "customer" ? (
        <div className="card-subtle">
          {canPublish
            ? "Approving will queue this draft for posting. You can keep the recommended timing or choose a specific date and time."
            : "Approving marks this draft as ready. Connect your X account in Settings when you want approved drafts to move into publishing."}
        </div>
      ) : null}
      {canPublish && scheduleLater ? (
        <label>
          <div className="field-label">Post at a specific time</div>
          <div className="card-subtle">Pick a custom posting time in {publishSettings?.timezone ?? "Asia/Kolkata"}.</div>
          <input
            className="editor"
            type="datetime-local"
            value={scheduledFor}
            min={minimumScheduleValue}
            onChange={(event) => setScheduledFor(event.target.value)}
          />
        </label>
      ) : null}
      {isOverLimit ? <div className="card-subtle">Shorten the text before approving ({Math.abs(charRemaining)} chars over limit).</div> : null}
      {initialStatus ? <div className="card-subtle">Current status: {initialStatus.replaceAll("_", " ")}.</div> : null}
      {lastAction === "approved" ? <div className="card-subtle">This draft will now leave the live review queue and move into the next publishing state.</div> : null}
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
