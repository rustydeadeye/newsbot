import type { Route } from "next";
import Link from "next/link";

import { formatOptionalDateTime, getFreshnessLabel, getFreshnessTone } from "@/lib/lifecycle-ui";
import { parseIsoDate } from "@/lib/publish-plan";
import { ViewerRole } from "@/lib/session";
import { ReviewItem } from "@/lib/types";

function overdueLabel(slaDueAt: string): string {
  const parsed = parseIsoDate(slaDueAt);
  if (!parsed) return "overdue";
  const hoursAgo = Math.round((Date.now() - parsed.getTime()) / 3_600_000);
  return hoursAgo > 0 ? `overdue · ${hoursAgo}h ago` : "overdue";
}

function getReasonLabel(reason: string, role: ViewerRole) {
  if (role === "customer") {
    if (reason.includes("guardrail") || reason.includes("blocked")) {
      return "needs extra review";
    }
    return "needs review";
  }
  return reason.replaceAll("_", " ");
}

function getTypeLabel(item: ReviewItem, role: ViewerRole) {
  if (role === "customer") {
    return "update";
  }
  return item.event?.event_type ?? "event";
}

export function QueueReviewRow({ item, href = "/drafts", role = "admin" }: { item: ReviewItem; href?: string; role?: ViewerRole }) {
  const freshnessLabel = role === "customer" ? getFreshnessLabel(item) : null;
  const freshnessTone = getFreshnessTone(item);
  const overdueTitle = formatOptionalDateTime(item.sla_due_at);
  return (
    <Link href={href as Route} className="queue-review-row queue-review-row-link">
      <div className="row space">
        <div className="row">
          <span className="pill">{getTypeLabel(item, role)}</span>
          <span className={item.reason.includes("guardrail") || item.reason.includes("blocked") ? "pill warn" : "pill"}>
            {getReasonLabel(item.reason, role)}
          </span>
          {item.overdue ? (
            <span className="pill warn" title={overdueTitle ?? undefined}>
              {item.sla_due_at ? overdueLabel(item.sla_due_at) : "overdue"}
            </span>
          ) : null}
        </div>
        <span className="mono">{item.event?.ticker ?? "MARKET"}</span>
      </div>
      <div className="queue-row-title">
        {String(item.event?.summary_facts?.headline ?? item.draft?.draft_text ?? "Untitled review item")}
      </div>
      {freshnessLabel ? <div className={`queue-row-lifecycle queue-row-lifecycle-${freshnessTone}`}>{freshnessLabel}</div> : null}
      <div className="card-subtle">
        Source {String(item.event?.summary_facts?.source_name ?? "Unknown")} | Score {item.event?.importance_score ?? "-"} |
        {" "}Confidence {item.event?.confidence_score ?? "-"}
      </div>
    </Link>
  );
}
