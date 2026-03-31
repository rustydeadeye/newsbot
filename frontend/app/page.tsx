import Link from "next/link";
import { redirect } from "next/navigation";

import { ApiErrorPanel } from "@/components/api-error-panel";
import { EmptyState } from "@/components/empty-state";
import { GenerateDraftsButton } from "@/components/generate-drafts-button";
import { GuidePanel } from "@/components/guide-panel";
import { KpiCard } from "@/components/kpi-card";
import { LeadReviewCard } from "@/components/lead-review-card";
import { PipelineRunButton } from "@/components/pipeline-run-button";
import { QueueReviewRow } from "@/components/queue-review-row";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getCurrentPipelineRun, getPublishJobs, getReviewQueue, getSources } from "@/lib/api";
import { ReviewItem } from "@/lib/types";
import { requireWorkspaceSession } from "@/lib/viewer";

export const revalidate = 30;

export default async function HomePage() {
  const { viewer, accessToken, onboarding } = await requireWorkspaceSession();
  const role = viewer.role;

  if (role === "customer" && onboarding && !onboarding.onboarding_completed) {
    redirect("/onboarding");
  }

  if (role === "admin") {
    let queue;
    let jobs;
    let sources;
    try {
      [queue, jobs, sources] = await Promise.all([
        getReviewQueue(accessToken),
        getPublishJobs(accessToken),
        getSources(accessToken),
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
    const sortedQueue = [...queue].sort((a: ReviewItem, b: ReviewItem) => {
      if (a.overdue !== b.overdue) return a.overdue ? -1 : 1;
      return (b.event?.importance_score ?? 0) - (a.event?.importance_score ?? 0);
    });

    return (
      <div className="page-grid">
        <ShellHeader
          title="Operations Home"
          description="Verify system health, queue pressure, and publishing readiness."
          viewer={viewer}
          freshnessLabel="Role-aware control center"
        />
        <div className="metrics">
          <KpiCard label="Pending Review" value={queue.length} detail="Open review items" tone={queue.length > 0 ? "warning" : "calm"} />
          <KpiCard label="Publish Failures" value={failed} detail="Delivery issues to resolve" tone={failed > 0 ? "danger" : "calm"} />
          <KpiCard label="Blocked Items" value={blocked} detail="Guardrail pressure" tone={blocked > 0 ? "warning" : "calm"} />
          <KpiCard label="Disabled Sources" value={disabledSources} detail="Coverage gaps" tone={disabledSources > 0 ? "danger" : "calm"} />
        </div>
        <StatusPanel
          eyebrow="Top priority"
          title={topFailure ? "Resolve publishing failures first" : "System flow is currently stable"}
          description={
            topFailure
              ? `Latest failure: ${topFailure.last_error ?? topFailure.result_message ?? "Unknown delivery error"}`
              : "No delivery failures are currently blocking output. Use the command center below to monitor queue and source readiness."
          }
          tone={topFailure ? "danger" : "default"}
        />
        <div className="row">
          <PipelineRunButton />
          <Link className="button secondary" href="/jobs">
            Open Publishing
          </Link>
        </div>
        {sortedQueue.length > 0 ? (
          <div className="panel">
            <div className="section-title">Needs intervention</div>
            <div className="queue-list">
              {sortedQueue.slice(0, 6).map((item) => (
                <QueueReviewRow key={item.id} item={item} />
              ))}
            </div>
          </div>
        ) : (
          <EmptyState
            title="No urgent intervention items"
            description="Review backlog, source controls, and delivery failures are all currently clear."
            action={
              <Link className="button secondary" href="/events">
                Review recent events
              </Link>
            }
          />
        )}
      </div>
    );
  }

  let queue;
  let currentRun = null;
  try {
    [queue, currentRun] = await Promise.all([getReviewQueue(accessToken), getCurrentPipelineRun(accessToken)]);
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

  const leadItem = queue[0] ?? null;
  const secondaryItems = queue.slice(1, 6);
  const highPriority = queue.filter((item: ReviewItem) => (item.event?.importance_score ?? 0) >= 80).length;
  const blocked = queue.filter((item: ReviewItem) => item.reason.includes("blocked") || item.reason.includes("guardrail")).length;
  const ready = queue.filter((item: ReviewItem) => Boolean(item.draft?.draft_text)).length;

  return (
    <div className="page-grid">
      <ShellHeader
        title="Home"
        description="Review what Newsbot found and decide what should move forward."
        viewer={viewer}
        freshnessLabel="Decision-first workspace"
      />
      <div className="metrics">
        <KpiCard label="Needs Review" value={queue.length} detail="Items waiting for your decision" />
        <KpiCard label="High Priority" value={highPriority} detail="Strong importance signals" tone={highPriority > 0 ? "warning" : "calm"} />
        <KpiCard label="Needs Attention" value={blocked} detail="Guardrail-triggered review" tone={blocked > 0 ? "warning" : "calm"} />
        <KpiCard label="Drafts Ready" value={ready} detail="Items with usable draft text" />
      </div>
      {currentRun ? (
        <StatusPanel
          eyebrow="Generation status"
          title={
            currentRun.status === "running" || currentRun.status === "queued"
              ? "Draft generation is in progress"
              : currentRun.status === "empty"
                ? "No matching events found"
                : currentRun.status === "failed"
                  ? "Draft generation needs attention"
                  : "Latest generation complete"
          }
          description={
            currentRun.status === "running" || currentRun.status === "queued"
              ? "Newsbot is preparing customer-specific drafts from the latest available events."
              : currentRun.status === "empty"
                ? "No recent events matched your current profile or watchlist. Update your settings or try again later."
                : currentRun.status === "failed"
                  ? (currentRun.error_message ?? "The latest generation run failed unexpectedly.")
                  : `Latest run created ${currentRun.result_counts.drafted ?? 0} drafts for review.`
          }
          tone={currentRun.status === "failed" ? "danger" : currentRun.status === "empty" ? "warning" : "default"}
        />
      ) : null}
      {queue.length === 0 ? (
        <EmptyState
          title="No drafts need review yet"
          description="Generate customer-specific drafts from the latest available events. When a draft needs a decision, it will appear here with the event context and next action."
          action={<GenerateDraftsButton />}
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
