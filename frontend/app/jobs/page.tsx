import { ApiErrorPanel } from "@/components/api-error-panel";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { getPublishJobs, getPublishLogs } from "@/lib/api";

export default async function JobsPage() {
  let jobs;
  let logs;
  try {
    [jobs, logs] = await Promise.all([getPublishJobs(), getPublishLogs()]);
  } catch (error) {
    return (
      <div className="page-grid">
        <PageHeader title="Publish Jobs" description="Delivery queue, failures, and posting history." />
        <ApiErrorPanel
          title="Publish jobs unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }
  const queued = jobs.filter((job) => job.status === "queued").length;
  const posted = jobs.filter((job) => job.status === "posted").length;
  const failed = jobs.filter((job) => job.status === "failed").length;

  return (
    <div className="page-grid">
      <PageHeader title="Publish Jobs" description="Delivery queue, failures, and posting history." />
      <div className="metrics">
        <MetricCard label="Queued" value={queued} />
        <MetricCard label="Posted" value={posted} />
        <MetricCard label="Failed" value={failed} />
        <MetricCard label="Recent Logs" value={logs.length} />
      </div>
      <div className="card-grid">
        <div className="panel">
          <div className="headline">Recent Jobs</div>
          <div className="log-list">
            {jobs.length === 0 ? <div className="empty">No publish jobs yet.</div> : null}
            {jobs.map((job) => (
              <div key={job.id} className="log-item">
                <div className="row space">
                  <span className={job.status === "failed" ? "pill danger" : "pill"}>{job.status}</span>
                  <span className="mono">{job.event?.ticker ?? "MARKET"}</span>
                </div>
                <div>{String(job.event?.summary_facts?.headline ?? job.draft?.draft_text ?? "Unknown job")}</div>
                <div className="card-subtle">
                  attempts {job.attempt_count} {job.last_error ? `| ${job.last_error}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="headline">Recent Publish Logs</div>
          <div className="log-list">
            {logs.length === 0 ? <div className="empty">No publish logs yet.</div> : null}
            {logs.map((log) => (
              <div key={log.id} className="log-item">
                <div className="row space">
                  <span className="pill">posted</span>
                  <span className="mono">{log.platform_post_id ?? "no-platform-id"}</span>
                </div>
                <div className="card-subtle">{log.posted_at ?? log.created_at}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
