import { ApiErrorPanel } from "@/components/api-error-panel";
import { EmptyState } from "@/components/empty-state";
import { GuidePanel } from "@/components/guide-panel";
import { QueueReviewRow } from "@/components/queue-review-row";
import { ReviewActions } from "@/components/review-actions";
import { ShellHeader } from "@/components/shell-header";
import { getReviewDrafts } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function DraftsPage() {
  const { viewer, accessToken } = await requireServerViewer();
  const role = viewer.role;
  let drafts;
  try {
    drafts = await getReviewDrafts(accessToken);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Drafts"
          description="Edit generated copy before it moves to the next stage."
          viewer={viewer}
          freshnessLabel="Draft editing workspace"
        />
        <ApiErrorPanel
          title="Draft review unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
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
      <GuidePanel
        eyebrow="Draft workspace"
        title={role === "admin" ? "Operational editing surface" : "Your content review surface"}
        description={
          role === "admin"
            ? "Use this screen when you want to edit in one place and manage queueing deliberately."
            : "Use this screen when you want more room to edit before approving or rejecting a draft."
        }
      />
      <div className="draft-list">
        {drafts.length === 0 ? (
          <EmptyState
            title="No drafts need review"
            description="When Newsbot needs help refining copy, those drafts will appear here."
          />
        ) : null}
        {drafts.map((draft) => (
          <div key={draft.id} className="draft-workbench">
            <div className="draft-workbench-main">
              <QueueReviewRow
                item={{
                  id: draft.id,
                  event_id: draft.event_id,
                  reason: draft.needs_review ? "manual_review" : "resolved",
                  assigned_to: null,
                  status: draft.status,
                  event: draft.event ?? null,
                  draft
                }}
              />
              <div className="draft-workbench-context">
                <div className="lead-review-block">
                  <div className="section-label">Source context</div>
                  <div className="card-subtle">{String(draft.event?.summary_facts?.source_name ?? "Unknown source")}</div>
                </div>
                <div className="lead-review-block">
                  <div className="section-label">Editing mode</div>
                  <div className="card-subtle">
                    {draft.needs_review
                      ? "Use this workspace for a deliberate pass before approving."
                      : "This draft has already moved out of the live review path."}
                  </div>
                </div>
              </div>
            </div>
            <div className="draft-workbench-editor">
              <ReviewActions draftId={draft.id} initialText={draft.draft_text} role={role} initialStatus={draft.status} compact />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
