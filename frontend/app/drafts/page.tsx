import Link from "next/link";
import { redirect } from "next/navigation";

import { ActiveRunRefresher } from "@/components/active-run-refresher";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { CustomerDegradedState } from "@/components/customer-degraded-state";
import { CustomerPublishJobActions } from "@/components/customer-publish-job-actions";
import { EmptyState } from "@/components/empty-state";
import { GenerateDraftsButton } from "@/components/generate-drafts-button";
import { GuidePanel } from "@/components/guide-panel";
import { QueueReviewRow } from "@/components/queue-review-row";
import { RejectedDraftsSection } from "@/components/rejected-drafts-section";
import { ReviewActions } from "@/components/review-actions";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getCurrentPipelineRun, getCustomerDraftsWorkspace } from "@/lib/api";
import { formatOptionalDateTime, getBucketLabel, getFreshnessLabel, getInactiveReasonCopy, getSafeText } from "@/lib/lifecycle-ui";
import { formatPublishTime } from "@/lib/publish-plan";
import { DraftSummary } from "@/lib/types";
import { requireWorkspaceSession } from "@/lib/viewer";

export default async function DraftsPage({
  searchParams,
}: {
  searchParams?: Promise<{ draftId?: string }>;
}) {
  const { viewer, accessToken, onboarding, onboardingError } = await requireWorkspaceSession();
  const role = viewer.role;
  const params = (await searchParams) ?? {};
  const selectedDraftId = params.draftId ? Number(params.draftId) : null;
  if (role === "customer" && onboardingError) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Drafts"
          description="Edit generated copy before it moves to the next stage."
          viewer={viewer}
          freshnessLabel="Draft editing workspace"
        />
        <CustomerDegradedState
          title="We could not finish loading your draft workspace"
          description="Newsbot had trouble loading your customer setup. Please try again shortly."
        />
      </div>
    );
  }
  if (role === "customer" && onboarding && !onboarding.onboarding_completed) {
    redirect("/onboarding");
  }
  let drafts;
  let approvedDrafts;
  let rejectedDrafts;
  let historyDrafts: DraftSummary[] = [];
  let currentRun = null;
  let customerSettings = null;
  try {
    if (role === "customer") {
      const [workspace, run] = await Promise.all([
        getCustomerDraftsWorkspace(accessToken),
        getCurrentPipelineRun(accessToken),
      ]);
      drafts = workspace.drafts;
      approvedDrafts = workspace.approved_drafts;
      rejectedDrafts = workspace.rejected_drafts;
      historyDrafts = workspace.history;
      customerSettings = workspace.settings;
      currentRun = run;
    } else {
      [drafts, approvedDrafts, rejectedDrafts, currentRun, customerSettings] = [[], [], [], null, null];
    }
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Drafts"
          description="Edit generated copy before it moves to the next stage."
          viewer={viewer}
          freshnessLabel="Draft editing workspace"
        />
        {role === "admin" ? (
          <AdminApiErrorPanel
            title="Draft review unavailable"
            detail={error instanceof Error ? error.message : "Unknown API error"}
          />
        ) : (
          <CustomerDegradedState
            title="We could not load your drafts right now"
            description="Newsbot had trouble opening your draft workspace. Please try again shortly."
          />
        )}
      </div>
    );
  }

  const isActiveRun = currentRun?.status === "queued" || currentRun?.status === "running";
  const sortedDrafts = selectedDraftId
    ? [...drafts].sort((a, b) => {
        if (a.id === selectedDraftId) return -1;
        if (b.id === selectedDraftId) return 1;
        return 0;
      })
    : drafts;
  const readyToPublishDrafts = approvedDrafts.filter((draft) => draft.status === "approved");
  const scheduledOrQueuedDrafts = approvedDrafts.filter((draft) => ["queued", "publishing"].includes(draft.status));
  const recentlyPostedDrafts = approvedDrafts.filter((draft) => draft.status === "posted");
  const needsAttentionDrafts = approvedDrafts.filter((draft) => draft.status === "failed");
  const inactiveHistoryDrafts = historyDrafts.filter((draft) => ["expired", "superseded", "rejected"].includes(draft.status));

  return (
    <div className="page-grid">
      <ActiveRunRefresher active={isActiveRun} />
      <ShellHeader
        eyebrow="Draft Editing Workspace"
        title="Drafts"
        description={
          role === "admin"
            ? "Refine copy, make the final decision, and control whether approved drafts are queued."
            : "Review the suggested copy, adjust the wording, and decide whether it is ready."
        }
        viewer={viewer}
        freshnessLabel={role === "admin" ? "Operational editing mode" : "Customer editing mode"}
      />
      {role === "customer" && isActiveRun ? (
        <StatusPanel
          eyebrow="Generation status"
          title={currentRun?.status === "queued" ? "Preparing drafts" : "Generating drafts"}
          description="Newsbot is still preparing new drafts. This page will refresh automatically when more review items are ready."
        />
      ) : null}
      <GuidePanel
        eyebrow="Draft workspace"
        title={role === "admin" ? "Operational editing surface" : "Your content review surface"}
        description={
          role === "admin"
            ? "Use this screen when you want to edit in one place and manage queueing deliberately."
            : "Use this screen when you want more room to edit before approving or rejecting a draft."
        }
      />
      {role === "customer" ? (
        <StatusPanel
          eyebrow="How this queue works"
          title="Active queue shows only currently actionable items"
          description="Fresh and overdue items stay here while they still deserve a decision. Older or replaced items move into history automatically."
        />
      ) : null}
      {role === "customer" ? (
        <div className="metrics metrics-compact">
          <div className="kpi-card">
            <div className="metric-label">Needs review</div>
            <div className="metric-value">{sortedDrafts.length}</div>
          </div>
          <div className="kpi-card">
            <div className="metric-label">Ready to publish</div>
            <div className="metric-value">{readyToPublishDrafts.length}</div>
          </div>
          <div className="kpi-card">
            <div className="metric-label">Scheduled next</div>
            <div className="metric-value">{scheduledOrQueuedDrafts.length}</div>
          </div>
        </div>
      ) : null}
      <div className="draft-list">
        {sortedDrafts.length === 0 ? (
          <EmptyState
            title={role === "customer" ? "No drafts are ready yet" : "No drafts need review"}
            description={
              role === "customer"
                ? "Newsbot only surfaces stronger finance updates here. Add a watchlist or generate again when more material events arrive."
                : "When Newsbot needs help refining copy, those drafts will appear here."
            }
            action={role === "customer" ? <GenerateDraftsButton /> : <Link href="/events" className="button secondary">View Events</Link>}
          />
        ) : null}
        {sortedDrafts.map((draft) => (
          <div key={draft.id} className={draft.id === selectedDraftId ? "draft-workbench draft-workbench-selected" : "draft-workbench"}>
            <div className="draft-workbench-main">
              <QueueReviewRow
                item={{
                  id: draft.id,
                  event_id: draft.event_id,
                  reason: draft.needs_review ? "manual_review" : "resolved",
                  assigned_to: null,
                  status: draft.status,
                  sla_due_at: null,
                  overdue: false,
                  event: draft.event ?? null,
                  draft
                }}
                href={`/drafts?draftId=${draft.id}`}
                role={role}
              />
              <div className="draft-workbench-context">
                  <div className="lead-review-block">
                    <div className="section-label">Source context</div>
                    <div className="card-subtle">{getSafeText(draft.event?.summary_facts?.source_name, "Unknown source")}</div>
                  {draft.event?.summary_facts?.document_url || draft.event?.summary_facts?.source_url ? (
                    <a
                      className="source-link"
                      href={String(draft.event.summary_facts.document_url ?? draft.event.summary_facts.source_url)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View source →
                    </a>
                  ) : null}
                </div>
                <div className="lead-review-block">
                  <div className="section-label">What this means now</div>
                  <div className="card-subtle">
                    {draft.id === selectedDraftId
                      ? "You opened this draft from Home. Keep refining here until you are ready to approve or reject it."
                      : draft.needs_review
                        ? "Use this workspace for a deliberate pass before approving."
                        : "This draft has already moved out of the live review path."}
                  </div>
                  {getFreshnessLabel(draft, customerSettings?.timezone) ? (
                    <div className="lifecycle-banner lifecycle-banner-inline lifecycle-banner-calm" style={{ marginTop: "0.75rem" }}>
                      {getFreshnessLabel(draft, customerSettings?.timezone)}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="draft-workbench-editor">
              <ReviewActions
                draftId={draft.id}
                initialText={draft.draft_text}
                role={role}
                initialStatus={draft.status}
                compact
                canPublish={Boolean(customerSettings?.x_connected)}
                publishSettings={customerSettings}
              />
            </div>
          </div>
        ))}
      </div>
      {role === "customer" && approvedDrafts.length > 0 ? (
        <div className="panel">
          <div className="section-title">Publishing workflow</div>
          {readyToPublishDrafts.length > 0 ? (
            <div className="stack" style={{ marginTop: "0.75rem" }}>
              <div className="section-label">Ready to publish</div>
              {readyToPublishDrafts.map((draft) => (
                <div key={`ready-${draft.id}`} className="publish-row">
                  <div className="row space">
                    <span className="pill">approved</span>
                    <span className="mono">{draft.event?.ticker ?? "MARKET"}</span>
                  </div>
                  <div className="queue-row-title">{getSafeText(draft.event?.summary_facts?.headline, draft.draft_text)}</div>
                  <div className="card-subtle">Approved and waiting for schedule. Choose when it should move forward.</div>
                  <div className="card-subtle">{draft.draft_text}</div>
                </div>
              ))}
            </div>
          ) : null}
          {scheduledOrQueuedDrafts.length > 0 ? (
            <div className="stack" style={{ marginTop: "0.75rem" }}>
              <div className="section-label">Scheduled</div>
              {scheduledOrQueuedDrafts.map((draft) => (
                <div key={`scheduled-${draft.id}`} className="publish-row">
                  <div className="row space">
                    <span className={draft.status === "publishing" ? "pill warn" : "pill subtle"}>
                      {getBucketLabel(draft.status, draft.lifecycle_state)}
                    </span>
                    <span className="mono">{draft.event?.ticker ?? "MARKET"}</span>
                  </div>
                  <div className="queue-row-title">{getSafeText(draft.event?.summary_facts?.headline, draft.draft_text)}</div>
                  <div className="card-subtle">{draft.draft_text}</div>
                  <div className="card-subtle">
                    {draft.publish_job?.scheduled_for
                      ? `Scheduled for ${formatPublishTime(draft.publish_job.scheduled_for, customerSettings?.timezone ?? "Asia/Kolkata")}`
                      : draft.status === "publishing"
                        ? "Queued for immediate publishing and moving through delivery now."
                        : "Queued for immediate publishing."}
                  </div>
                  {draft.publish_job ? (
                    <CustomerPublishJobActions
                      jobId={draft.publish_job.id}
                      status={draft.publish_job.status}
                      scheduledFor={draft.publish_job.scheduled_for}
                      settings={customerSettings}
                      freshUntil={draft.fresh_until}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {needsAttentionDrafts.length > 0 ? (
            <div className="stack" style={{ marginTop: "0.75rem" }}>
              <div className="section-label">Needs attention</div>
              {needsAttentionDrafts.map((draft) => (
                <div key={`attention-${draft.id}`} className="publish-row failed">
                  <div className="row space">
                    <span className="pill danger">Needs attention</span>
                    <span className="mono">{draft.event?.ticker ?? "MARKET"}</span>
                  </div>
                  <div className="queue-row-title">{getSafeText(draft.event?.summary_facts?.headline, draft.draft_text)}</div>
                  <div className="card-subtle">Publishing did not complete. Review the item and retry or move it back to approved.</div>
                  {draft.publish_job ? (
                    <CustomerPublishJobActions
                      jobId={draft.publish_job.id}
                      status={draft.publish_job.status}
                      scheduledFor={draft.publish_job.scheduled_for}
                      settings={customerSettings}
                      freshUntil={draft.fresh_until}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {recentlyPostedDrafts.length > 0 ? (
            <div className="stack" style={{ marginTop: "0.75rem" }}>
              <div className="section-label">Recently posted</div>
              {recentlyPostedDrafts.map((draft) => (
                <div key={`posted-${draft.id}`} className="publish-row">
                  <div className="row space">
                    <span className="pill subtle">posted</span>
                    <span className="mono">{draft.event?.ticker ?? "MARKET"}</span>
                  </div>
                  <div className="queue-row-title">{getSafeText(draft.event?.summary_facts?.headline, draft.draft_text)}</div>
                  <div className="card-subtle">Posted successfully.</div>
                  <div className="card-subtle">{draft.draft_text}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {role === "admin" && rejectedDrafts.length > 0 ? (
        <RejectedDraftsSection drafts={rejectedDrafts} />
      ) : null}
      {role === "customer" && inactiveHistoryDrafts.length > 0 ? (
        <div className="panel">
          <div className="section-title">History</div>
          <div className="stack" style={{ marginTop: "0.75rem" }}>
            {inactiveHistoryDrafts.map((draft) => (
              <div key={`history-${draft.id}`} className="publish-row">
                <div className="row space">
                  <span className="pill subtle">{(draft.lifecycle_state ?? draft.status).replaceAll("_", " ")}</span>
                  <span className="card-subtle">
                    {formatOptionalDateTime(draft.updated_at, customerSettings?.timezone) ?? ""}
                  </span>
                </div>
                <div className="queue-row-title">{getSafeText(draft.event?.summary_facts?.headline, draft.draft_text)}</div>
                <div className="card-subtle">{getInactiveReasonCopy(draft.inactive_reason) ?? draft.draft_text}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
