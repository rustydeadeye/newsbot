import { AccessDenied } from "@/components/access-denied";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { KpiCard } from "@/components/kpi-card";
import { PublishQueuePanel } from "@/components/publish-queue-panel";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getPublishJobs, getPublishLogs } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function JobsPage() {
  const { viewer, accessToken } = await requireServerViewer();
  const role = viewer.role;
  if (role !== "admin") {
    return <AccessDenied title="Publishing" description="Track delivery queue health, failures, and posting outcomes." />;
  }
  let jobs;
  let logs;
  try {
    [jobs, logs] = await Promise.all([getPublishJobs(accessToken), getPublishLogs(accessToken)]);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Publishing"
          description="Delivery queue, failures, and posting history."
          viewer={viewer}
          freshnessLabel="Operational delivery workspace"
        />
        <AdminApiErrorPanel
          title="Publishing unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }
  const queued = jobs.filter((job) => job.status === "queued").length;
  const posted = jobs.filter((job) => job.status === "posted").length;
  const failed = jobs.filter((job) => job.status === "failed").length;
  const publishing = jobs.filter((job) => job.status === "publishing").length;

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Publishing Operations"
        title="Publishing"
        description="Track queue movement, recover failures, and confirm what actually posted."
        viewer={viewer}
        freshnessLabel="Delivery queue and posting outcomes"
      />
      <div className="metrics">
        <KpiCard label="Queued" value={queued} detail="Waiting to publish" tone={queued > 0 ? "warning" : "calm"} />
        <KpiCard label="In Flight" value={publishing} detail="Currently publishing" />
        <KpiCard label="Failed" value={failed} detail="Needs intervention" tone={failed > 0 ? "danger" : "calm"} />
        <KpiCard label="Posted" value={posted} detail="Recent published jobs" />
        <KpiCard label="Recent Logs" value={logs.length} detail="Recent posted activity" />
      </div>
      <StatusPanel
        eyebrow="Operational priority"
        title={failed > 0 ? "Resolve delivery failures first" : "Delivery flow is healthy"}
        description={
          failed > 0
            ? "Publishing failures sit at the top of the admin workflow because they directly affect trust and output."
            : "No failures are blocking output. Use the queue view below to monitor movement and recent delivery activity."
        }
        tone={failed > 0 ? "danger" : "default"}
      />
      <PublishQueuePanel jobs={jobs} logs={logs} />
    </div>
  );
}
