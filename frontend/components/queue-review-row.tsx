import Link from "next/link";

import { ReviewItem } from "@/lib/types";

function overdueLabel(slaDueAt: string): string {
  const hoursAgo = Math.round((Date.now() - new Date(slaDueAt).getTime()) / 3_600_000);
  return hoursAgo > 0 ? `overdue · ${hoursAgo}h ago` : "overdue";
}

export function QueueReviewRow({ item }: { item: ReviewItem }) {
  return (
    <Link href="/drafts" className="queue-review-row queue-review-row-link">
      <div className="row space">
        <div className="row">
          <span className="pill">{item.event?.event_type ?? "event"}</span>
          <span className={item.reason.includes("guardrail") ? "pill warn" : "pill"}>
            {item.reason.replaceAll("_", " ")}
          </span>
          {item.overdue ? (
            <span className="pill warn" title={item.sla_due_at ?? undefined}>
              {item.sla_due_at ? overdueLabel(item.sla_due_at) : "overdue"}
            </span>
          ) : null}
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
    </Link>
  );
}
