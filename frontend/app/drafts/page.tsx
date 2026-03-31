import Link from "next/link";
import { redirect } from "next/navigation";

import { ActiveRunRefresher } from "@/components/active-run-refresher";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { CustomerDegradedState } from "@/components/customer-degraded-state";
import { EmptyState } from "@/components/empty-state";
import { GenerateDraftsButton } from "@/components/generate-drafts-button";
import { GuidePanel } from "@/components/guide-panel";
import { QueueReviewRow } from "@/components/queue-review-row";
import { RejectedDraftsSection } from "@/components/rejected-drafts-section";
import { ReviewActions } from "@/components/review-actions";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getApprovedDrafts, getCreatorSettings, getCurrentPipelineRun, getRejectedDrafts, getReviewDrafts } from "@/lib/api";
import { formatPublishTime } from "@/lib/publish-plan";
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
  let currentRun = null;
  let customerSettings = null;
  try {
    [drafts, approvedDrafts, rejectedDrafts, currentRun, customerSettings] = await Promise.all([
      getReviewDrafts(accessToken),
      role === "customer" ? getApprovedDrafts(accessToken) : Promise.resolve([]),
      getRejectedDrafts(accessToken),
      role === "customer" ? getCurrentPipelineRun(accessToken) : Promise.resolve(null),
      role === "customer" ? getCreatorSettings(accessToken) : Promise.resolve(null),
    ]);
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
      {role === "customer" && approvedDrafts.length > 0 ? (
        <StatusPanel
          eyebrow="Approved drafts"
          title={
            approvedDrafts.find((draft) => draft.publish_job?.scheduled_for)
              ? `Next scheduled post: ${formatPublishTime(
                  approvedDrafts.find((draft) => draft.publish_job?.scheduled_for)?.publish_job?.scheduled_for as string,
                  customerSettings?.timezone ?? "Asia/Kolkata"
                )}`
              : "Approved drafts are waiting in your publishing flow"
          }
          description="Approved drafts no longer disappear. Keep editing below, and use the approved section to track what will post next."
        />
      ) : null}
      <div className="draft-list">
        {sortedDrafts.length === 0 ? (
          <EmptyState
            title={role === "customer" ? "No drafts are ready yet" : "No drafts need review"}
            description={
              role === "customer"
                ? "Generate drafts from the latest updates or come back when new review items are ready."
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
                  <div className="card-subtle">{String(draft.event?.summary_facts?.source_name ?? "Unknown source")}</div>
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
                  <div className="section-label">Editing mode</div>
                  <div className="card-subtle">
                    {draft.id === selectedDraftId
                      ? "You opened this draft from Home. Keep refining here until you are ready to approve or reject it."
                      : draft.needs_review
                        ? "Use this workspace for a deliberate pass before approving."
                        : "This draft has already moved out of the live review path."}
                  </div>
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
          <div className="section-title">Approved & scheduled</div>
          <div className="stack" style={{ marginTop: "0.75rem" }}>
            {approvedDrafts.map((draft) => (
              <div key={draft.id} className="publish-row">
                <div className="row space">
                  <span className={draft.status === "posted" ? "pill success" : draft.status === "queued" ? "pill warn" : "pill"}>
                    {draft.status.replaceAll("_", " ")}
                  </span>
                  <span className="mono">{draft.event?.ticker ?? "MARKET"}</span>
                </div>
                <div className="queue-row-title">{String(draft.event?.summary_facts?.headline ?? draft.draft_text)}</div>
                <div className="card-subtle">{draft.draft_text}</div>
                <div className="card-subtle">
                  {draft.publish_job?.scheduled_for
                    ? `Scheduled for ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
                        new Date(draft.publish_job.scheduled_for)
                      )}`
                    : draft.publish_job
                      ? "Queued for immediate publishing"
                      : "Approved and waiting for your next publishing step"}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {rejectedDrafts.length > 0 ? (
        <RejectedDraftsSection drafts={rejectedDrafts} />
      ) : null}
    </div>
  );
}
