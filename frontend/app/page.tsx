import Link from "next/link";
import { redirect } from "next/navigation";

import { ActiveRunRefresher } from "@/components/active-run-refresher";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { CustomerDegradedState } from "@/components/customer-degraded-state";
import { EmptyState } from "@/components/empty-state";
import { GenerateDraftsButton } from "@/components/generate-drafts-button";
import { GuidePanel } from "@/components/guide-panel";
import { KpiCard } from "@/components/kpi-card";
import { LeadReviewCard } from "@/components/lead-review-card";
import { PipelineRunButton } from "@/components/pipeline-run-button";
import { QueueReviewRow } from "@/components/queue-review-row";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getCurrentPipelineRun, getCustomerHomeWorkspace, getPublishJobs, getReviewQueue, getSources } from "@/lib/api";
import { formatPublishTime } from "@/lib/publish-plan";
import { CustomerWorkspaceState, PipelineRun, ReviewItem } from "@/lib/types";
import { requireWorkspaceSession } from "@/lib/viewer";

export const revalidate = 30;

function getCustomerWorkspaceState(queue: ReviewItem[], currentRun: PipelineRun | null): CustomerWorkspaceState {
  if (queue.length > 0) {
    return "generation_ready";
  }
  if (currentRun?.status === "queued" || currentRun?.status === "running") {
    return "generation_in_progress";
  }
  if (currentRun?.status === "empty") {
    return "generation_no_matches";
  }
  if (currentRun?.status === "failed") {
    return "temporary_issue";
  }
  return "ready_to_generate";
}

export default async function HomePage() {
  const { viewer, accessToken, onboarding, onboardingError } = await requireWorkspaceSession();
  const role = viewer.role;

  if (role === "customer" && onboardingError) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Home"
          description="Review what Newsbot found and decide what should move forward."
          viewer={viewer}
          freshnessLabel="Decision-first workspace"
        />
        <CustomerDegradedState
          title="We could not finish opening your workspace"
          description="Newsbot had trouble loading your setup state. Please try again shortly."
        />
      </div>
    );
  }

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
          <AdminApiErrorPanel
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
                <QueueReviewRow key={item.id} item={item} role="admin" />
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
  let customerSettings = null;
  let approvedDrafts = [];
  try {
    const [workspace, run] = await Promise.all([
      getCustomerHomeWorkspace(accessToken),
      getCurrentPipelineRun(accessToken),
    ]);
    queue = workspace.queue;
    approvedDrafts = workspace.approved_drafts;
    customerSettings = workspace.settings;
    currentRun = run;
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Home"
          description="Review what Newsbot found and decide what should move forward."
          viewer={viewer}
          freshnessLabel="Decision-first workspace"
        />
        <CustomerDegradedState
          title="We hit a temporary issue loading your review workspace"
          description="Newsbot could not load your drafts just now. Please try again shortly."
        />
      </div>
    );
  }

  const state = getCustomerWorkspaceState(queue, currentRun);
  const runIsActive = currentRun?.status === "queued" || currentRun?.status === "running";
  const leadItem = queue[0] ?? null;
  const secondaryItems = queue.slice(1, 6);
  const highPriority = queue.filter((item: ReviewItem) => (item.event?.importance_score ?? 0) >= 80).length;
  const ready = queue.filter((item: ReviewItem) => Boolean(item.draft?.draft_text)).length;
  const showCustomerMetrics = state === "generation_ready";
  const nextScheduledDraft = approvedDrafts.find((draft) => draft.publish_job?.scheduled_for);
  const postedCount = approvedDrafts.filter((draft) => draft.status === "posted").length;
  const queuedCount = approvedDrafts.filter((draft) => draft.status === "queued").length;
  const publishingCount = approvedDrafts.filter((draft) => draft.status === "publishing").length;
  const failedCount = approvedDrafts.filter((draft) => draft.status === "failed").length;

  return (
    <div className="page-grid">
      <ActiveRunRefresher active={runIsActive} />
      <ShellHeader
        title="Home"
        description="Review what Newsbot found and decide what should move forward."
        viewer={viewer}
        freshnessLabel="Decision-first workspace"
      />
      {showCustomerMetrics ? (
        <div className="metrics metrics-compact">
          <KpiCard label="Needs Review" value={queue.length} detail="Items waiting for your decision" />
          <KpiCard label="High Priority" value={highPriority} detail="Strong importance signals" tone={highPriority > 0 ? "warning" : "calm"} />
          <KpiCard label="Drafts Ready" value={ready} detail="Items with usable draft text" />
        </div>
      ) : null}
      {state === "generation_in_progress" ? (
        <StatusPanel
          eyebrow="Generation status"
          title={currentRun?.status === "queued" ? "Preparing drafts" : "Generating drafts"}
          description="Newsbot is creating customer-specific drafts from recent updates. This page will refresh automatically when the run finishes."
        />
      ) : null}
      {state === "generation_no_matches" ? (
        <StatusPanel
          eyebrow="Generation status"
          title="No high-signal finance updates matched your setup"
          description="Newsbot skipped low-value or generic filings this run. Add companies or topics to your watchlist, or try again when stronger updates arrive."
          tone="warning"
        />
      ) : null}
      {state === "temporary_issue" ? (
        <CustomerDegradedState
          title="Draft generation needs attention"
          description={currentRun?.error_message ?? "Newsbot could not prepare new drafts right now. Please try again shortly."}
        />
      ) : null}
      {state === "ready_to_generate" ? (
        <EmptyState
          title="Generate your first drafts"
          description="Newsbot is ready to create draft posts from the latest updates in your coverage. Once they are ready, you will review them here before anything can move ahead."
          action={<GenerateDraftsButton />}
        />
      ) : null}
      {state === "generation_no_matches" ? (
        <EmptyState
          title="Nothing high-signal needs review right now"
          description="This run only surfaces stronger finance updates. Update your watchlist for tighter relevance, or try again when more material news arrives."
          action={<GenerateDraftsButton label="Try again" />}
        />
      ) : null}
      {state === "generation_ready" ? (
        <div className="customer-home-grid">
          <div className="customer-home-main">
            {leadItem ? (
              <LeadReviewCard
                item={leadItem}
                role={role}
                canPublish={Boolean(customerSettings?.x_connected)}
                publishSettings={customerSettings}
              />
            ) : null}
          </div>
          <GuidePanel
            eyebrow="How this works"
            title="One lead decision at a time"
            description="Newsbot finds recent updates, drafts the post, and sends anything uncertain or sensitive here for your approval. Nothing is treated as ready until you review it."
          >
            <div className="workspace-list">
              <div className="workspace-list-row">
                <span>Approve</span>
                <strong>when the wording is ready to move forward</strong>
              </div>
              <div className="workspace-list-row">
                <span>Reject</span>
                <strong>when the draft needs a rewrite or should be held</strong>
              </div>
              <div className="workspace-list-row">
                <span>Events</span>
                <strong>gives you story context, not required work</strong>
              </div>
            </div>
          </GuidePanel>
        </div>
      ) : null}
      {state === "generation_ready" && approvedDrafts.length > 0 ? (
        <StatusPanel
          eyebrow="Publishing activity"
          title={
            failedCount > 0
              ? "Some approved drafts need attention"
              : publishingCount > 0
                ? "A draft is publishing right now"
                : nextScheduledDraft?.publish_job?.scheduled_for
              ? `Next post: ${formatPublishTime(nextScheduledDraft.publish_job.scheduled_for, customerSettings?.timezone ?? "Asia/Kolkata")}`
              : queuedCount > 0
                ? "Approved drafts are queued for publishing"
                : postedCount > 0
                  ? "Your recent approved drafts have already posted"
                  : "Approved drafts are waiting for your next publishing step"
          }
          description={
            failedCount > 0
              ? `${failedCount} approved draft${failedCount === 1 ? "" : "s"} hit a delivery issue. Open Drafts to review what needs to be retried or adjusted.`
              : publishingCount > 0
                ? `${publishingCount} draft${publishingCount === 1 ? "" : "s"} ${publishingCount === 1 ? "is" : "are"} actively moving through publishing right now.`
              : nextScheduledDraft?.publish_job?.scheduled_for
              ? `Newsbot will send your next approved draft at the scheduled time. You can review the full list in Drafts.`
              : queuedCount > 0
                ? `${queuedCount} approved draft${queuedCount === 1 ? "" : "s"} ${queuedCount === 1 ? "is" : "are"} in the publishing queue right now.`
                : postedCount > 0
                  ? `${postedCount} draft${postedCount === 1 ? "" : "s"} already made it through publishing.`
                  : "Approved drafts stay visible in Drafts until you decide when they should move forward."
          }
          tone={failedCount > 0 ? "danger" : publishingCount > 0 ? "warning" : "default"}
        />
      ) : null}
      {state === "generation_ready" && secondaryItems.length > 0 ? (
        <div className="panel">
          <div className="section-title">Up next</div>
          <div className="queue-list">
            {secondaryItems.map((item) => (
              <QueueReviewRow key={item.id} item={item} href={`/drafts?draftId=${item.draft?.id ?? item.id}`} role="customer" />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
