"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { cancelPublishJob, reschedulePublishJob, retryPublishJob } from "@/lib/api";
import { formatOptionalDateTime, getNextAvailableSlot } from "@/lib/lifecycle-ui";
import { formatPublishTime, toIsoString } from "@/lib/publish-plan";
import { CreatorSettings } from "@/lib/types";

export function CustomerPublishJobActions({
  jobId,
  status,
  scheduledFor: currentScheduledFor,
  settings,
  freshUntil,
}: {
  jobId: number;
  status: string;
  scheduledFor?: string | null;
  settings?: CreatorSettings | null;
  freshUntil?: string | null;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [customScheduledFor, setCustomScheduledFor] = useState("");
  const nextSlot = settings ? getNextAvailableSlot(settings) : null;
  const minimumScheduleValue = new Date(Date.now() + 60_000).toISOString().slice(0, 16);

  function saveSchedule(value: string) {
    startTransition(async () => {
      try {
        await reschedulePublishJob(jobId, value);
        setMessage("Schedule updated.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Reschedule failed");
      }
    });
  }

  function onCancel() {
    startTransition(async () => {
      try {
        await cancelPublishJob(jobId);
        setMessage("Moved back to approved.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Cancel failed");
      }
    });
  }

  function onRetry() {
    startTransition(async () => {
      try {
        await retryPublishJob(jobId);
        setMessage("Queued again.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Retry failed");
      }
    });
  }

  function onReschedule() {
    if (!customScheduledFor) {
      setMessage("Choose a future time first.");
      return;
    }
    const iso = toIsoString(customScheduledFor);
    if (!iso) {
      setMessage("Choose a valid future time first.");
      return;
    }
    saveSchedule(iso);
  }

  return (
    <div className="stack publish-action-panel" style={{ marginTop: "0.75rem" }}>
      <div className="publish-plan-card">
        <div className="section-label">Scheduling</div>
        <div className="publish-plan-title">
          {currentScheduledFor && settings
            ? `Currently set for ${formatPublishTime(currentScheduledFor, settings.timezone ?? "Asia/Kolkata")}`
            : "Choose what should happen next"}
        </div>
        {settings ? <div className="card-subtle">Timezone: {settings.timezone ?? "Asia/Kolkata"}</div> : null}
        {freshUntil && settings ? (
          <div className="card-subtle">This item may be canceled automatically if it becomes stale after {formatPublishTime(freshUntil, settings.timezone ?? "Asia/Kolkata")}.</div>
        ) : null}
        {nextSlot ? (
          <div className="publish-action-inline">
            <div className="card-subtle">{nextSlot.label}</div>
            <button className="button secondary" disabled={isPending} onClick={() => saveSchedule(nextSlot.iso)}>
              {isPending ? "Saving…" : "Use next available slot"}
            </button>
          </div>
        ) : null}
      </div>
      <div className="actions">
        {status === "failed" ? (
          <button className="button secondary" disabled={isPending} onClick={onRetry}>
            {isPending ? "Retrying…" : "Retry publish"}
          </button>
        ) : null}
        {status === "queued" || status === "cancelled" || status === "skipped" || status === "failed" ? (
          <>
            <input
              className="editor compact"
              type="datetime-local"
              value={customScheduledFor}
              onChange={(event) => setCustomScheduledFor(event.target.value)}
              min={minimumScheduleValue}
            />
            <button className="button secondary" disabled={isPending} onClick={onReschedule}>
              {isPending ? "Saving…" : "Reschedule"}
            </button>
          </>
        ) : null}
        {status === "queued" || status === "skipped" ? (
          <button className="button secondary" disabled={isPending} onClick={onCancel}>
            {isPending ? "Moving…" : "Move back to approved"}
          </button>
        ) : null}
      </div>
      <div className="card-subtle">
        Custom schedules must be in the future and may still be limited by your posting window.
      </div>
      {currentScheduledFor ? (
        <div className="card-subtle">Current schedule: {formatOptionalDateTime(currentScheduledFor, settings?.timezone) ?? "Time unavailable"}</div>
      ) : null}
      {message ? <div className="card-subtle">{message}</div> : null}
    </div>
  );
}
