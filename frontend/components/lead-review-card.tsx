import { ReviewActions } from "@/components/review-actions";
import { ViewerRole } from "@/lib/session";
import { ReviewItem } from "@/lib/types";

function getLifecycleLabel(status: string) {
  if (status === "open") {
    return "Needs review";
  }
  return status.replaceAll("_", " ");
}

export function LeadReviewCard({
  item,
  role
}: {
  item: ReviewItem;
  role: ViewerRole;
}) {
  return (
    <div className="lead-review-card">
      <div className="lead-review-top">
        <div className="row">
          <span className="pill">{item.event?.event_type ?? "event"}</span>
          <span className={item.reason.includes("guardrail") ? "pill warn" : "pill"}>
            {item.reason.replaceAll("_", " ")}
          </span>
        </div>
        <span className="mono">{item.event?.ticker ?? "MARKET"}</span>
      </div>
      <div className="lead-review-copy">
        <div>
          <div className="section-label">What happened</div>
          <h3>{String(item.event?.summary_facts?.headline ?? item.draft?.draft_text ?? "Untitled review item")}</h3>
        </div>
        {item.event?.summary_facts?.document_url || item.event?.summary_facts?.source_url ? (
          <a
            className="source-link"
            href={String(item.event.summary_facts.document_url ?? item.event.summary_facts.source_url)}
            target="_blank"
            rel="noopener noreferrer"
          >
            View source document →
          </a>
        ) : null}
        <div className="lead-review-grid">
          <div className="lead-review-block">
            <div className="section-label">Why this needs review</div>
            <p className="card-subtle">
              {item.reason.includes("guardrail")
                ? "This item tripped a guardrail and needs a human decision before it can move forward."
                : "This draft needs your approval before Newsbot can treat it as ready."}
            </p>
          </div>
          <div className="lead-review-block">
            <div className="section-label">Lifecycle</div>
            <div className="workspace-subtle">
              <strong>{getLifecycleLabel(item.status)}</strong>
              <span>{String(item.event?.summary_facts?.source_name ?? "Unknown source")}</span>
            </div>
          </div>
        </div>
        <div className="lead-review-grid">
          <div className="lead-review-block">
            <div className="section-label">Suggested draft text</div>
            <div className="draft-surface">{item.draft?.draft_text ?? "No draft attached"}</div>
          </div>
          <div className="lead-review-block">
            <div className="section-label">Supporting metadata</div>
            <div className="support-metadata">
              <div className="support-row">
                <span>Source</span>
                <strong>{String(item.event?.summary_facts?.source_name ?? "Unknown source")}</strong>
              </div>
              <div className="support-row">
                <span>Score</span>
                <strong>{item.event?.importance_score ?? "-"}</strong>
              </div>
              <div className="support-row">
                <span>Confidence</span>
                <strong>{item.event?.confidence_score ?? "-"}</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
      {item.draft ? (
        <div className="lead-review-actions">
          <ReviewActions
            draftId={item.draft.id}
            initialText={item.draft.draft_text}
            role={role}
            initialStatus={item.draft.status}
            compact
          />
        </div>
      ) : null}
    </div>
  );
}
