import { AccessDenied } from "@/components/access-denied";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { KpiCard } from "@/components/kpi-card";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { WireFeedQueuePanel } from "@/components/wire-feed-queue-panel";
import { getWireJobs, getWireLogs } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function OperationsPage() {
  const { viewer, accessToken } = await requireServerViewer();
  if (viewer.role !== "admin") {
    return <AccessDenied title="Operations" description="Monitor queue health, publishing outcomes, and what the runtime is doing across products." />;
  }

  let wireJobs;
  let wireLogs;
  try {
    [wireJobs, wireLogs] = await Promise.all([getWireJobs(accessToken), getWireLogs(accessToken)]);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Operations"
          description="Live queue health, posting outcomes, and operator controls across finance and AI products."
          viewer={viewer}
          freshnessLabel="Live operations workspace"
        />
        <AdminApiErrorPanel
          title="Operations unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  const { queued, publishing, failed, skipped, aiJobs, financeJobs, webJobs, baseJobs } = wireJobs.reduce(
    (acc, job) => {
      if (job.status === "queued") acc.queued += 1;
      else if (job.status === "publishing") acc.publishing += 1;
      else if (job.status === "failed") acc.failed += 1;
      else if (job.status === "skipped") acc.skipped += 1;
      const product = job.candidate?.product ?? "finance";
      if (product === "ai") acc.aiJobs += 1;
      else acc.financeJobs += 1;
      const family = job.candidate?.source_family ?? "base";
      if (family === "web") acc.webJobs += 1;
      else acc.baseJobs += 1;
      return acc;
    },
    { queued: 0, publishing: 0, failed: 0, skipped: 0, aiJobs: 0, financeJobs: 0, webJobs: 0, baseJobs: 0 },
  );

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Operations"
        title="Operations"
        description="Monitor the shared publishing runtime, inspect queue quality, and keep posting healthy across products."
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
        title={failed > 0 ? "Clear publishing failures first" : "Publishing runtime is healthy"}
        description={
          failed > 0
            ? "Resolve publishing failures before trusting new queued posts. This page is the single control surface for the live runtime."
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
