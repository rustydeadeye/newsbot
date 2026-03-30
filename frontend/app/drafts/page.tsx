import { ApiErrorPanel } from "@/components/api-error-panel";
import { PageHeader } from "@/components/page-header";
import { ReviewActions } from "@/components/review-actions";
import { getReviewDrafts } from "@/lib/api";

export default async function DraftsPage() {
  let drafts;
  try {
    drafts = await getReviewDrafts();
  } catch (error) {
    return (
      <div className="page-grid">
        <PageHeader title="Draft Review" description="Edit AI-generated copy before it goes into the publish queue." />
        <ApiErrorPanel
          title="Draft review unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
      <PageHeader title="Draft Review" description="Edit AI-generated copy before it goes into the publish queue." />
      <div className="draft-list">
        {drafts.length === 0 ? <div className="panel empty">No drafts need review.</div> : null}
        {drafts.map((draft) => (
          <div key={draft.id} className="panel">
            <div className="row space">
              <div className="row">
                <span className="pill">{draft.event?.event_type ?? "draft"}</span>
                <span className={draft.status === "rejected" ? "pill danger" : "pill warn"}>{draft.status}</span>
              </div>
              <div className="mono">{draft.event?.ticker ?? "MARKET"}</div>
            </div>
            <div className="headline">{String(draft.event?.summary_facts?.headline ?? draft.draft_text)}</div>
            <ReviewActions draftId={draft.id} initialText={draft.draft_text} />
          </div>
        ))}
      </div>
    </div>
  );
}
