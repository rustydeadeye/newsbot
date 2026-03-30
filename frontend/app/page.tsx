import Link from "next/link";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { EmptyState } from "@/components/empty-state";
import { GuidePanel } from "@/components/guide-panel";
import { KpiCard } from "@/components/kpi-card";
import { LeadReviewCard } from "@/components/lead-review-card";
import { QueueReviewRow } from "@/components/queue-review-row";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getPublishJobs, getReviewQueue, getSources } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function HomePage() {
  const { viewer, accessToken } = await requireServerViewer();
  const role = viewer.role;

  if (role === "admin") {
    let queue;
    let jobs;
    let sources;
    try {
      [queue, jobs, sources] = await Promise.all([
        getReviewQueue(accessToken),
        getPublishJobs(accessToken),
        getSources(accessToken)
      ]);
    } catch (error) {
      return (
        <div className="page-grid">
          <ShellHeader
            title="Operations Home"
            description="Verify system health, queue pressure, and publishing readiness."
            viewer={viewer}
            freshnessLabel="Role-aware control center"
          />
          <ApiErrorPanel
            title="Operations overview unavailable"
            detail={error instanceof Error ? error.message : "Unknown API error"}
          />
        </div>
      );
    }

    const queued = jobs.filter((job) => job.status === "queued" || job.status === "publishing").length;
    const failed = jobs.filter((job) => job.status === "failed").length;
    const blocked = queue.filter((item) => item.reason.includes("guardrail")).length;
    const disabledSources = sources.filter((source) => !source.enabled).length;
    const topFailure = jobs.find((job) => job.status === "failed");

    return (
      <div className="page-grid">
        <ShellHeader
          eyebrow="Admin Command Center"
          title="Operations Home"
          description="Keep the pipeline healthy, spot delivery issues early, and jump straight to the work that needs intervention."
          viewer={viewer}
          freshnessLabel="Publishing, source, and review status"
          actions={
            <>
              <Link className="button" href="/jobs">
                Open Publishing
              </Link>
              <Link className="button secondary" href="/settings">
                Review Settings
              </Link>
            </>
          }
        />
        <div className="metrics">
          <KpiCard label="Open Review" value={queue.length} detail="Items waiting for a human decision" />
          <KpiCard label="Publishing Queue" value={queued} detail="Queued or in flight" tone={queued > 0 ? "warning" : "calm"} />
          <KpiCard label="Failures" value={failed} detail="Delivery errors that need intervention" tone={failed > 0 ? "danger" : "calm"} />
          <KpiCard label="Disabled Sources" value={disabledSources} detail="Coverage gaps affecting ingestion" tone={disabledSources > 0 ? "warning" : "calm"} />
        </div>
        <div className="command-center-grid">
          <StatusPanel
            eyebrow="Priority one"
            title={failed > 0 ? "Publishing failure needs intervention" : "Delivery is stable"}
            description={
              failed > 0
                ? `Start with the publish failure impacting output${topFailure?.event?.ticker ? ` for ${topFailure.event.ticker}` : ""}. Delivery issues rank above source and review backlog.`
                : "No active publish failures are blocking output right now. You can move on to source readiness and review pressure."
            }
            tone={failed > 0 ? "danger" : "default"}
          >
            {topFailure ? (
              <div className="workspace-list">
                <div className="workspace-list-row">
                  <span>{String(topFailure.event?.summary_facts?.headline ?? topFailure.draft?.draft_text ?? "Unknown failed job")}</span>
                  <strong>{topFailure.last_error ?? "See publishing details"}</strong>
                </div>
              </div>
            ) : null}
          </StatusPanel>
          <StatusPanel
            eyebrow="Secondary priority"
            title={disabledSources > 0 ? "Source coverage needs attention" : "Source coverage is healthy"}
            description={
              disabledSources > 0
                ? `${disabledSources} source${disabledSources === 1 ? " is" : "s are"} disabled. Fix coverage next so the queue stays trustworthy.`
                : "All configured sources are enabled. Review backlog is your next operational signal."
            }
            tone={disabledSources > 0 ? "warning" : "default"}
          />
        </div>
        <div className="card-grid admin-secondary-grid">
          <div className="panel">
            <div className="section-title">Review pressure</div>
            <div className="queue-list">
              <div className="card-subtle">
                {queue.length > 0
                  ? `${blocked} guardrail hold${blocked === 1 ? "" : "s"} and ${queue.length - blocked} standard review item${queue.length - blocked === 1 ? "" : "s"} are waiting.`
                  : "No review backlog is building right now."}
              </div>
              {queue.slice(0, 4).map((item) => (
                <QueueReviewRow key={item.id} item={item} />
              ))}
            </div>
          </div>
          <GuidePanel
            eyebrow="Fast actions"
            title="Move quickly without losing context"
            description="Use Publishing for delivery failures, Drafts for deliberate copy fixes, and Settings for source readiness or ownership changes."
          >
            <div className="inline-actions">
              <Link className="button" href="/drafts">
                Open Drafts
              </Link>
              <Link className="button secondary" href="/events">
                View Events
              </Link>
            </div>
          </GuidePanel>
        </div>
      </div>
    );
  }

  let queue;
  try {
    queue = await getReviewQueue(accessToken);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Home"
          description="Review what Newsbot found and decide what should move forward."
          viewer={viewer}
          freshnessLabel="Decision-first workspace"
        />
        <ApiErrorPanel
          title="Review queue unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }
  const highPriority = queue.filter((item) => (item.event?.importance_score ?? 0) >= 85).length;
  const blocked = queue.filter((item) => item.reason.includes("guardrail")).length;
  const ready = queue.filter((item) => item.draft).length;
  const leadItem = queue[0] ?? null;
  const secondaryItems = queue.slice(1, 5);

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Customer Review Workspace"
        title="Home"
        description="Start with the next item that needs your decision, then review the draft and approve or reject with confidence."
        viewer={viewer}
        freshnessLabel="Decision-first workspace"
        actions={
          <Link className="button secondary" href="/drafts">
            Open Drafts
          </Link>
        }
      />
      <div className="metrics">
        <KpiCard label="Needs Review" value={queue.length} detail="Items waiting for your decision" />
        <KpiCard label="High Priority" value={highPriority} detail="Strong importance signals" tone={highPriority > 0 ? "warning" : "calm"} />
        <KpiCard label="Needs Attention" value={blocked} detail="Guardrail-triggered review" tone={blocked > 0 ? "warning" : "calm"} />
        <KpiCard label="Drafts Ready" value={ready} detail="Items with usable draft text" />
      </div>
      {queue.length === 0 ? (
        <EmptyState
          title="Nothing needs review right now"
          description="Newsbot is still monitoring your sources. When a draft needs a decision, it will appear here with the event context and next action."
          action={
            <Link className="button secondary" href="/events">
              View recent events
            </Link>
          }
        />
      ) : (
        <div className="customer-home-grid">
          <div className="customer-home-main">
            {leadItem ? <LeadReviewCard item={leadItem} role={role} /> : null}
          </div>
          <GuidePanel
            eyebrow="How this works"
            title="One lead decision at a time"
            description="Newsbot gathers updates, drafts the post, and sends anything uncertain or sensitive here for your approval before it can move ahead."
          >
            <div className="workspace-list">
              <div className="workspace-list-row">
                <span>Approve</span>
                <strong>when the wording is ready</strong>
              </div>
              <div className="workspace-list-row">
                <span>Reject</span>
                <strong>when the post should be rewritten or held</strong>
              </div>
              <div className="workspace-list-row">
                <span>Events</span>
                <strong>gives you extra context, not required work</strong>
              </div>
            </div>
          </GuidePanel>
        </div>
      )}
      {secondaryItems.length > 0 ? (
        <div className="panel">
          <div className="section-title">Up next</div>
          <div className="queue-list">
            {secondaryItems.map((item) => (
              <QueueReviewRow key={item.id} item={item} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
