import { AccessDenied } from "@/components/access-denied";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { KpiCard } from "@/components/kpi-card";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { WireFeedQueuePanel } from "@/components/wire-feed-queue-panel";
import { getWireJobs, getWireLogs } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function WireFeedPage() {
  const { viewer, accessToken } = await requireServerViewer();
  if (viewer.role !== "admin") {
    return <AccessDenied title="Wire Feed" description="Monitor queue health, publishing outcomes, and what the runtime is doing across products." />;
  }

  let wireJobs;
  let wireLogs;
  try {
    [wireJobs, wireLogs] = await Promise.all([getWireJobs(accessToken), getWireLogs(accessToken)]);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Wire Feed"
          description="Live queue health, posting outcomes, and operator controls across finance and AI autopost products."
          viewer={viewer}
          freshnessLabel="Live operator workspace"
        />
        <AdminApiErrorPanel
          title="Wire feed unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  const queued = wireJobs.filter((job) => job.status === "queued").length;
  const publishing = wireJobs.filter((job) => job.status === "publishing").length;
  const failed = wireJobs.filter((job) => job.status === "failed").length;
  const skipped = wireJobs.filter((job) => job.status === "skipped").length;
  const aiJobs = wireJobs.filter((job) => job.candidate?.product === "ai").length;
  const financeJobs = wireJobs.filter((job) => (job.candidate?.product ?? "finance") === "finance").length;
  const webJobs = wireJobs.filter((job) => job.candidate?.source_family === "web").length;
  const baseJobs = wireJobs.filter((job) => (job.candidate?.source_family ?? "base") === "base").length;

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Operator Runtime"
        title="Wire Feed"
        description="Monitor the shared autopost runtime, inspect queue quality, and keep publishing healthy across products."
        viewer={viewer}
        freshnessLabel="Queue, skips, retries, and recent posts"
      />
      <div className="metrics">
        <KpiCard label="Queued" value={queued} detail="Waiting to publish" tone={queued > 0 ? "warning" : "calm"} />
        <KpiCard label="In Flight" value={publishing} detail="Currently publishing" />
        <KpiCard label="Failed" value={failed} detail="Needs intervention" tone={failed > 0 ? "danger" : "calm"} />
        <KpiCard label="Skipped" value={skipped} detail="Rejected by safety or queue rules" />
        <KpiCard label="Recent Logs" value={wireLogs.length} detail="Recent posting outcomes" />
      </div>
      <StatusPanel
        eyebrow="Operator focus"
        title={failed > 0 ? "Clear wire-feed failures first" : "Wire-feed runtime is healthy"}
        description={
          failed > 0
            ? "Resolve publishing failures before trusting new queued posts. This view is the single control surface for the live autopost runtime."
            : "Use this page to inspect queue quality, duplicate handling, retries, and what the shared runtime actually published."
        }
        tone={failed > 0 ? "danger" : "default"}
      >
        <div className="workspace-list">
          <div className="workspace-list-row">
            <span>Finance jobs in view</span>
            <strong>{financeJobs}</strong>
          </div>
          <div className="workspace-list-row">
            <span>AI jobs in view</span>
            <strong>{aiJobs}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Base pipeline activity</span>
            <strong>{baseJobs}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Web pipeline activity</span>
            <strong>{webJobs}</strong>
          </div>
        </div>
      </StatusPanel>
      <WireFeedQueuePanel jobs={wireJobs} logs={wireLogs} />
    </div>
  );
}
