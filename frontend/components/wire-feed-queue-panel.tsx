"use client";

import { useState, useTransition } from "react";

import { cancelWireJob, retryWireJob } from "@/lib/api";
import { formatOptionalDateTime, formatPipelineLabel } from "@/lib/lifecycle-ui";
import { WireJob, WirePublishLog } from "@/lib/types";

const WIRE_REASON_LABELS: Record<string, string> = {
  duplicate_cooldown: "Skipped — too similar to a recent wire post",
  duplicate_active_job: "Skipped — similar wire job is already active",
  hourly_limit: "Held — hourly wire cap reached",
  daily_limit: "Held — daily wire cap reached",
  rate_limited: "Held — X rate limit reached",
  retry_scheduled: "Held — retry scheduled after a publish error",
  cancelled_by_admin: "Cancelled by admin",
  manual_retry: "Queued again by admin",
};

function formatProductLabel(product?: string) {
  return product === "ai" ? "AI" : "Finance";
}

export function WireFeedQueuePanel({
  jobs: initialJobs,
  logs
}: {
  jobs: WireJob[];
  logs: WirePublishLog[];
}) {
  const [jobs, setJobs] = useState(initialJobs);
  const [actionErrors, setActionErrors] = useState<Record<number, string>>({});
  const [isPending, startTransition] = useTransition();

  function clearError(jobId: number) {
    setActionErrors((prev) => {
      const next = { ...prev };
      delete next[jobId];
      return next;
    });
  }

  function onRetry(jobId: number) {
    clearError(jobId);
    startTransition(async () => {
      try {
        const updated = await retryWireJob(jobId);
        setJobs((prev) => prev.map((job) => (job.id === jobId ? { ...job, ...updated } : job)));
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [jobId]: error instanceof Error ? error.message : "Retry failed" }));
      }
    });
  }

  function onCancel(jobId: number) {
    clearError(jobId);
    startTransition(async () => {
      try {
        const updated = await cancelWireJob(jobId);
        setJobs((prev) => prev.map((job) => (job.id === jobId ? { ...job, ...updated } : job)));
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [jobId]: error instanceof Error ? error.message : "Cancel failed" }));
      }
    });
  }

  return (
    <div className="publishing-layout">
      <div className="panel">
        <div className="section-title">Scheduled queue</div>
        <div className="card-subtle">Everything waiting to publish next, with the product and pipeline that created it.</div>
        <div className="log-list">
          {jobs.length === 0 ? <div className="empty">No jobs are waiting right now. When new posts are approved, they will appear here.</div> : null}
          {jobs.map((job) => {
            const message = job.result_message ? (WIRE_REASON_LABELS[job.result_message] ?? job.result_message) : null;
            const product = job.candidate?.product;
            const sourceFamily = job.candidate?.source_family;
            return (
              <div key={job.id} className={`publish-row${job.status === "failed" ? " failed" : ""}`}>
                <div className="row space">
                  <div className="row">
                    <span className={
                      job.status === "failed" ? "pill danger"
                      : job.status === "queued" ? "pill warn"
                      : job.status === "publishing" ? "pill"
                      : "pill"
                    }>
                      {job.status}
                    </span>
                    <span className="pill">{job.priority}</span>
                    <span className="pill subtle">{formatProductLabel(product)}</span>
                    <span className="pill subtle">{sourceFamily === "web" ? "Web" : "Base"}</span>
                    <span className="mono">{job.candidate?.ticker ?? "MARKET"}</span>
                    <span className="card-subtle">
                      {formatPipelineLabel(product, sourceFamily, job.candidate?.lane, job.candidate?.source_name)}
                    </span>
                  </div>
                  <span className="card-subtle">attempts {job.attempt_count}</span>
                </div>
                <div className="queue-row-title">{job.candidate?.draft_text ?? job.candidate?.title ?? "Unknown wire job"}</div>
                <div className="card-subtle">{job.candidate?.title ?? "No source title available"}</div>
                {message ? <div className="card-subtle">{message}</div> : null}
                {job.last_error ? <div className="card-subtle">Failure detail: {job.last_error}</div> : null}
                {job.scheduled_for ? (
                  <div className="card-subtle">Scheduled for {formatOptionalDateTime(job.scheduled_for) ?? "Time unavailable"}</div>
                ) : null}
                {actionErrors[job.id] ? <div className="card-subtle">{actionErrors[job.id]}</div> : null}
                {job.status === "failed" || job.status === "skipped" || job.status === "cancelled" ? (
                  <div className="actions">
                    <button className="button secondary" disabled={isPending} onClick={() => onRetry(job.id)}>
                      Retry
                    </button>
                  </div>
                ) : null}
                {job.status === "queued" || job.status === "publishing" ? (
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
        <div className="section-title">Recent published posts</div>
        <div className="card-subtle">A simple log of what the runtime successfully pushed out most recently.</div>
        <div className="log-list">
          {logs.length === 0 ? <div className="empty">No published posts yet. Successful posts will appear here with their product and pipeline labels.</div> : null}
          {logs.map((log) => (
            <div key={log.id} className="publish-log-row">
              <div className="row space">
                <div className="row">
                  <span className="pill">posted</span>
                  <span className="pill subtle">{formatProductLabel(log.candidate?.product)}</span>
                  <span className="pill subtle">{log.candidate?.source_family === "web" ? "Web" : "Base"}</span>
                  <span className="card-subtle">
                    {formatPipelineLabel(log.candidate?.product, log.candidate?.source_family, log.candidate?.lane, log.candidate?.source_name)}
                  </span>
                </div>
                <span className="mono">{log.platform_post_id ?? "no-platform-id"}</span>
              </div>
              <div className="queue-row-title">{log.candidate?.draft_text ?? log.candidate?.title ?? "Unknown wire post"}</div>
              <div className="card-subtle">{log.candidate?.title ?? "No source title available"}</div>
              <div className="card-subtle">Posted at {formatOptionalDateTime(log.posted_at ?? log.created_at) ?? "Time unavailable"}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
