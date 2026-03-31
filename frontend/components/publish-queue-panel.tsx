"use client";

import { useState, useTransition } from "react";

import { cancelPublishJob, retryPublishJob } from "@/lib/api";
import { PublishJob, PublishLog } from "@/lib/types";

const SKIP_REASON_LABELS: Record<string, string> = {
  outside_posting_window: "Held — outside posting window",
  cooldown_duplicate: "Held — too similar to a recent post",
  rate_limit_hourly: "Held — hourly post cap reached",
  duplicate_draft_job: "Skipped — already queued",
  dry_run: "Dry run — not posted",
  cancelled_by_admin: "Cancelled by admin",
};

function formatScheduled(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function PublishQueuePanel({
  jobs: initialJobs,
  logs
}: {
  jobs: PublishJob[];
  logs: PublishLog[];
}) {
  const [jobs, setJobs] = useState(initialJobs);
  const [actionErrors, setActionErrors] = useState<Record<number, string>>({});
  const [isPending, startTransition] = useTransition();

  function clearError(jobId: number) {
    setActionErrors((prev) => { const next = { ...prev }; delete next[jobId]; return next; });
  }

  function onRetry(jobId: number) {
    setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: "queued", last_error: null } : j)));
    clearError(jobId);
    startTransition(async () => {
      try {
        const updated = await retryPublishJob(jobId);
        setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: updated.status } : j)));
      } catch (error) {
        setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: "failed" } : j)));
        setActionErrors((prev) => ({ ...prev, [jobId]: error instanceof Error ? error.message : "Retry failed" }));
      }
    });
  }

  function onCancel(jobId: number) {
    setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: "cancelled" } : j)));
    clearError(jobId);
    startTransition(async () => {
      try {
        const updated = await cancelPublishJob(jobId);
        setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: updated.status } : j)));
      } catch (error) {
        setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, status: "queued" } : j)));
        setActionErrors((prev) => ({ ...prev, [jobId]: error instanceof Error ? error.message : "Cancel failed" }));
      }
    });
  }

  return (
    <div className="publishing-layout">
      <div className="panel">
        <div className="section-title">Live queue state</div>
        <div className="log-list">
          {jobs.length === 0 ? <div className="empty">No publish jobs yet.</div> : null}
          {jobs.map((job) => {
            const isFuture = job.scheduled_for && new Date(job.scheduled_for) > new Date();
            const displayMessage = job.result_message
              ? (SKIP_REASON_LABELS[job.result_message] ?? job.result_message)
              : job.last_error
                ? `Failure detail: ${job.last_error}`
                : "No active failure detail.";

            return (
              <div key={job.id} className={`publish-row${job.status === "failed" ? " failed" : ""}`}>
                <div className="row space">
                  <div className="row">
                    <span className={
                      job.status === "failed" ? "pill danger"
                      : job.status === "queued" ? "pill warn"
                      : job.status === "cancelled" ? "pill"
                      : "pill"
                    }>
                      {job.status}
                    </span>
                    <span className="mono">{job.event?.ticker ?? "MARKET"}</span>
                  </div>
                  <span className="card-subtle">attempts {job.attempt_count}</span>
                </div>
                <div className="queue-row-title">
                  {String(job.event?.summary_facts?.headline ?? job.draft?.draft_text ?? "Unknown delivery job")}
                </div>
                <div className="card-subtle">{displayMessage}</div>
                {isFuture ? (
                  <div className="card-subtle">Scheduled for {formatScheduled(job.scheduled_for!)}</div>
                ) : null}
                {actionErrors[job.id] ? <div className="card-subtle">{actionErrors[job.id]}</div> : null}
                {job.status === "failed" || job.status === "skipped" ? (
                  <div className="actions">
                    <button className="button secondary" disabled={isPending} onClick={() => onRetry(job.id)}>
                      Retry
                    </button>
                  </div>
                ) : job.status === "queued" ? (
                  <div className="actions">
                    <button className="button danger" disabled={isPending} onClick={() => onCancel(job.id)}>
                      Cancel
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
      <div className="panel">
        <div className="section-title">Recent posting outcomes</div>
        <div className="log-list">
          {logs.length === 0 ? <div className="empty">No publish logs yet.</div> : null}
          {logs.map((log) => {
            const eng = log.engagement_stats ?? {};
            const hasEngagement = Object.keys(eng).length > 0;
            return (
              <div key={log.id} className="publish-log-row">
                <div className="row space">
                  <span className="pill">posted</span>
                  <span className="mono">{log.platform_post_id ?? "no-platform-id"}</span>
                </div>
                <div className="card-subtle">Posted at {log.posted_at ?? log.created_at}</div>
                {hasEngagement ? (
                  <div className="card-subtle">
                    {typeof eng.like_count !== "undefined" ? `Likes: ${eng.like_count}` : null}
                    {typeof eng.retweet_count !== "undefined" ? ` · RT: ${eng.retweet_count}` : null}
                    {typeof eng.impression_count !== "undefined" ? ` · Views: ${eng.impression_count}` : null}
                  </div>
                ) : (
                  <div className="card-subtle">Engagement pending — views and likes load after 24h.</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
