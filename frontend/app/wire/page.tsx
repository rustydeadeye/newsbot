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
    return <AccessDenied title="Wire Feed" description="Monitor the experimental market-wire queue, failures, and posted items." />;
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
          description="Experimental market-wire queue, posting outcomes, and operator controls."
          viewer={viewer}
          freshnessLabel="Live wire-feed operations"
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

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Experimental Runtime"
        title="Wire Feed"
        description="Manage the separate market-wire system without mixing it into the original publishing workflow."
        viewer={viewer}
        freshnessLabel="Queue, skips, retries, and posted wire items"
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
            ? "This page is the control surface for the separate wire-feed branch. Resolve failures before increasing automation or trusting the queue."
            : "Use this page to inspect queue quality, duplicate handling, retries, and what the wire-feed worker actually attempted to publish."
        }
        tone={failed > 0 ? "danger" : "default"}
      />
      <WireFeedQueuePanel jobs={wireJobs} logs={wireLogs} />
    </div>
  );
}
