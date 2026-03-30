import { ReviewItem } from "@/lib/types";

export function QueueReviewRow({ item }: { item: ReviewItem }) {
  return (
    <div className="queue-review-row">
      <div className="row space">
        <div className="row">
          <span className="pill">{item.event?.event_type ?? "event"}</span>
          <span className={item.reason.includes("guardrail") ? "pill warn" : "pill"}>
            {item.reason.replaceAll("_", " ")}
          </span>
        </div>
        <span className="mono">{item.event?.ticker ?? "MARKET"}</span>
      </div>
      <div className="queue-row-title">
        {String(item.event?.summary_facts?.headline ?? item.draft?.draft_text ?? "Untitled review item")}
      </div>
      <div className="card-subtle">
        Source {String(item.event?.summary_facts?.source_name ?? "Unknown")} | Score {item.event?.importance_score ?? "-"} |
        {" "}Confidence {item.event?.confidence_score ?? "-"}
      </div>
    </div>
  );
}
