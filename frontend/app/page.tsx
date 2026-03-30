import { ApiErrorPanel } from "@/components/api-error-panel";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { ReviewActions } from "@/components/review-actions";
import { getReviewQueue } from "@/lib/api";

export default async function HomePage() {
  let queue;
  try {
    queue = await getReviewQueue();
  } catch (error) {
    return (
      <div className="page-grid">
        <PageHeader title="Review Queue" description="Editorial control over automated finance posts." />
        <ApiErrorPanel
          title="Review queue unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }
  const highPriority = queue.filter((item) => (item.event?.importance_score ?? 0) >= 85).length;
  const blocked = queue.filter((item) => item.reason.includes("guardrail")).length;

  return (
    <div className="page-grid">
      <PageHeader
        title="Review Queue"
        description="Editorial control over automated finance posts. Approve only what should actually go live."
      />
      <div className="metrics">
        <MetricCard label="Open Review Items" value={queue.length} />
        <MetricCard label="High Priority" value={highPriority} />
        <MetricCard label="Guardrail Holds" value={blocked} />
        <MetricCard label="Ready to Clear" value={queue.filter((item) => item.draft).length} />
      </div>
      <div className="queue-list">
        {queue.length === 0 ? <div className="panel empty">No open review items.</div> : null}
        {queue.map((item) => (
          <div key={item.id} className="panel">
            <div className="row space">
              <div className="row">
                <span className="pill">{item.event?.event_type ?? "event"}</span>
                <span className={item.reason.includes("guardrail") ? "pill warn" : "pill"}>
                  {item.reason.replaceAll("_", " ")}
                </span>
              </div>
              <div className="mono">{item.event?.ticker ?? "MARKET"}</div>
            </div>
            <div className="headline">
              {String(item.event?.summary_facts?.headline ?? item.draft?.draft_text ?? "Untitled review item")}
            </div>
            <div className="meta-grid">
              <div>
                <span className="field-label">Current Draft</span>
                <div>{item.draft?.draft_text ?? "No draft attached"}</div>
              </div>
              <div>
                <span className="field-label">Event Facts</span>
                <div className="card-subtle">
                  {String(item.event?.summary_facts?.source_name ?? "Unknown source")} | Score{" "}
                  {item.event?.importance_score ?? "-"} | Confidence {item.event?.confidence_score ?? "-"}
                </div>
              </div>
            </div>
            {item.draft ? <ReviewActions draftId={item.draft.id} initialText={item.draft.draft_text} /> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
