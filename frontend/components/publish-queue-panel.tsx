import { PublishJob, PublishLog } from "@/lib/types";

export function PublishQueuePanel({
  jobs,
  logs
}: {
  jobs: PublishJob[];
  logs: PublishLog[];
}) {
  return (
    <div className="publishing-layout">
      <div className="panel">
        <div className="section-title">Live queue state</div>
        <div className="log-list">
          {jobs.length === 0 ? <div className="empty">No publish jobs yet.</div> : null}
          {jobs.map((job) => (
            <div key={job.id} className={`publish-row${job.status === "failed" ? " failed" : ""}`}>
              <div className="row space">
                <div className="row">
                  <span className={job.status === "failed" ? "pill danger" : job.status === "queued" ? "pill warn" : "pill"}>
                    {job.status}
                  </span>
                  <span className="mono">{job.event?.ticker ?? "MARKET"}</span>
                </div>
                <span className="card-subtle">attempts {job.attempt_count}</span>
              </div>
              <div className="queue-row-title">
                {String(job.event?.summary_facts?.headline ?? job.draft?.draft_text ?? "Unknown delivery job")}
              </div>
              <div className="card-subtle">
                {job.last_error
                  ? `Failure detail: ${job.last_error}`
                  : job.result_message
                    ? job.result_message
                    : "No active failure detail."}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="section-title">Recent posting outcomes</div>
        <div className="log-list">
          {logs.length === 0 ? <div className="empty">No publish logs yet.</div> : null}
          {logs.map((log) => (
            <div key={log.id} className="publish-log-row">
              <div className="row space">
                <span className="pill">posted</span>
                <span className="mono">{log.platform_post_id ?? "no-platform-id"}</span>
              </div>
              <div className="card-subtle">Posted at {log.posted_at ?? log.created_at}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
