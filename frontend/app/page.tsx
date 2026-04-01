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
import { formatOptionalDateTime, getActivityLabel, getInactiveReasonCopy } from "@/lib/lifecycle-ui";
import { getRoleHomePath, IS_AUTOPOST_MODE } from "@/lib/product-mode";
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

  if (IS_AUTOPOST_MODE) {
    redirect(getRoleHomePath(role));
  }

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
  let sinceLastSeenAt: string | null = null;
  let sinceLastSeenSummary = {};
  let recentActivity = [];
  try {
    const [workspace, run] = await Promise.all([
      getCustomerHomeWorkspace(accessToken),
      getCurrentPipelineRun(accessToken),
    ]);
    queue = workspace.queue;
    approvedDrafts = workspace.approved_drafts;
    customerSettings = workspace.settings;
    sinceLastSeenAt = workspace.since_last_seen_at ?? null;
    sinceLastSeenSummary = workspace.since_last_seen_summary;
    recentActivity = workspace.recent_activity;
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
  const readyToPublishCount = approvedDrafts.filter((draft) => draft.status === "approved").length;
  const nextScheduledDraft = approvedDrafts.find((draft) => draft.publish_job?.scheduled_for);
  const postedCount = approvedDrafts.filter((draft) => draft.status === "posted").length;
  const queuedCount = approvedDrafts.filter((draft) => draft.status === "queued").length;
  const publishingCount = approvedDrafts.filter((draft) => draft.status === "publishing").length;
  const failedCount = approvedDrafts.filter((draft) => draft.status === "failed").length;
  const sinceAttention = recentActivity.filter((item) => ["failed", "expired", "superseded"].includes(item.status));
  const sinceCompletedCount = Number((sinceLastSeenSummary as Record<string, number>).posted ?? 0);
  const briefingHasActivity = sinceAttention.length > 0 || sinceCompletedCount > 0;
  const sinceAnchor = formatOptionalDateTime(sinceLastSeenAt, customerSettings?.timezone);

  return (
    <div className="page-grid">
      <ActiveRunRefresher active={runIsActive} />
      <ShellHeader
        title="Home"
        description="Review what Newsbot found and decide what should move forward."
        viewer={viewer}
        freshnessLabel="Decision-first workspace"
      />
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
        approvedDrafts.length > 0 ? (
          <StatusPanel
            eyebrow="What needs your attention now"
            title={nextScheduledDraft?.publish_job?.scheduled_for ? "Nothing needs review right now" : "No review items are waiting right now"}
            description={
              nextScheduledDraft?.publish_job?.scheduled_for
                ? `Your next scheduled post is set for ${formatPublishTime(nextScheduledDraft.publish_job.scheduled_for, customerSettings?.timezone ?? "Asia/Kolkata")}. Open Drafts if you want to change the schedule or review approved items.`
                : readyToPublishCount > 0
                  ? `${readyToPublishCount} approved draft${readyToPublishCount === 1 ? "" : "s"} ${readyToPublishCount === 1 ? "is" : "are"} ready for a publishing decision in Drafts.`
                  : "Nothing needs review right now. Newsbot will keep this workspace current as stronger updates arrive."
            }
          />
        ) : (
          <EmptyState
            title="Generate your first drafts"
            description="Newsbot is ready to create draft posts from the latest updates in your coverage. Once they are ready, you will review them here before anything can move ahead."
            action={<GenerateDraftsButton />}
          />
        )
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
            {secondaryItems.length > 0 ? (
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
          <div className="stack">
            <GuidePanel
              eyebrow="Publishing summary"
              title="What can move forward next"
              description="Home stays focused on action now. Use this summary to see what is ready, scheduled, or needs attention."
            >
              <div className="workspace-list">
                <div className="workspace-list-row">
                  <span>Ready to publish</span>
                  <strong>{readyToPublishCount}</strong>
                </div>
                <div className="workspace-list-row">
                  <span>Scheduled</span>
                  <strong>{queuedCount + publishingCount}</strong>
                </div>
                <div className="workspace-list-row">
                  <span>Needs attention</span>
                  <strong>{failedCount}</strong>
                </div>
              </div>
            </GuidePanel>
            {nextScheduledDraft?.publish_job?.scheduled_for ? (
              <StatusPanel
                eyebrow="Scheduled next"
                title={formatPublishTime(nextScheduledDraft.publish_job.scheduled_for, customerSettings?.timezone ?? "Asia/Kolkata")}
                description="This is the next approved item currently set to move through publishing."
              />
            ) : null}
            {(Object.keys(sinceLastSeenSummary).length > 0 || recentActivity.length > 0 || sinceAnchor) ? (
              <div className="panel">
                <div className="section-title">Since you were away</div>
                {sinceAnchor ? <div className="card-subtle">Since {sinceAnchor}</div> : null}
                {!briefingHasActivity ? (
                  <div className="card-subtle" style={{ marginTop: "0.75rem" }}>Nothing important changed while you were away.</div>
                ) : (
                  <div className="stack" style={{ marginTop: "0.75rem" }}>
                    <div className="workspace-list">
                      <div className="workspace-list-row">
                        <span>Posted</span>
                        <strong>{sinceCompletedCount}</strong>
                      </div>
                      <div className="workspace-list-row">
                        <span>Needs attention</span>
                        <strong>{sinceAttention.length}</strong>
                      </div>
                    </div>
                    {sinceAttention.length > 0 ? (
                      <div className="stack">
                        {sinceAttention.slice(0, 3).map((item) => (
                          <div key={`${item.status}-${item.draft_id}`} className={`publish-row ${item.status === "failed" ? "failed" : ""}`}>
                            <div className="row space">
                              <span className="pill warn">{getActivityLabel(item.status)}</span>
                              <span className="card-subtle">{formatOptionalDateTime(item.updated_at, customerSettings?.timezone) ?? ""}</span>
                            </div>
                            <div className="queue-row-title">{item.headline}</div>
                            {item.inactive_reason ? <div className="card-subtle">{getInactiveReasonCopy(item.inactive_reason)}</div> : null}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
