import Link from "next/link";
import { redirect } from "next/navigation";

import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { CustomerDegradedState } from "@/components/customer-degraded-state";
import { EmptyState } from "@/components/empty-state";
import { GuidePanel } from "@/components/guide-panel";
import { ShellHeader } from "@/components/shell-header";
import { getEvents } from "@/lib/api";
import { getRoleHomePath, IS_AUTOPOST_MODE } from "@/lib/product-mode";
import { requireWorkspaceSession } from "@/lib/viewer";

const DRAFT_STATUS_LABELS: Record<string, string> = {
  draft: "in review",
  approved: "approved",
  queued: "queued",
  posted: "posted",
  rejected: "rejected",
  failed: "failed",
};

export default async function EventsPage() {
  const { viewer, accessToken, onboarding, onboardingError } = await requireWorkspaceSession();
  const role = viewer.role;

  if (IS_AUTOPOST_MODE) {
    redirect(getRoleHomePath(role));
  }

  if (role === "customer" && onboardingError) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Events"
          description="Track what Newsbot has identified across your coverage."
          viewer={viewer}
          freshnessLabel="Context and coverage view"
        />
        <CustomerDegradedState
          title="We could not finish loading your workspace"
          description="Newsbot had trouble loading your customer setup. Please try again shortly."
        />
      </div>
    );
  }
  if (role === "customer" && onboarding && !onboarding.onboarding_completed) {
    redirect("/onboarding");
  }
  let events;
  try {
    events = await getEvents(accessToken);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Events"
          description="Track what Newsbot has identified across your coverage."
          viewer={viewer}
          freshnessLabel="Context and coverage view"
        />
        {role === "admin" ? (
          <AdminApiErrorPanel
            title="Events feed unavailable"
            detail={error instanceof Error ? error.message : "Unknown API error"}
          />
        ) : (
          <CustomerDegradedState
            title="We could not load your update context right now"
            description="Newsbot had trouble opening the latest story context. Please try again shortly."
          />
        )}
      </div>
    );
  }

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Event Intelligence"
        title="Events"
        description={
          role === "admin"
            ? "Inspect the normalized event stream with operational scoring context."
            : "See the underlying events Newsbot is tracking so you can understand what each draft is based on."
        }
        viewer={viewer}
        freshnessLabel={role === "admin" ? "Operational context stream" : "Supporting context for review"}
      />
      <GuidePanel
        eyebrow="Coverage view"
        title={role === "admin" ? "Operations-friendly event feed" : "What happened and why it matters"}
        description={
          role === "admin"
            ? "Use this screen to spot clusters, confidence shifts, and event quality before they become publishing issues."
            : "Use this screen when you want more context behind the content Newsbot is asking you to review."
        }
      />
      {events.length === 0 ? (
        <EmptyState
          title="No recent events"
          description="As Newsbot ingests new source items, the event feed will populate here."
        />
      ) : null}
      <div className="events-grid">
        {events.map((event) => (
          <div key={event.id} className="event-card">
            <div className="row space">
              <div className="row">
                <span className="pill">{event.event_type}</span>
                <span className="mono">{event.ticker ?? "MARKET"}</span>
              </div>
              <span className="event-score">Score {event.importance_score}</span>
            </div>
            <div className="queue-row-title">{String(event.summary_facts.headline ?? event.entity_name ?? event.event_type)}</div>
            <div className="event-card-meta">
              <div className="card-subtle">Source {String(event.summary_facts.source_name ?? "Unknown")}</div>
              <div className="card-subtle">Confidence {event.confidence_score}</div>
            </div>
            {role === "admin" && event.dedupe_key ? <div className="mono event-detail">{event.dedupe_key}</div> : null}
            {event.draft_status ? (
              <div className="row space">
                <span className={event.draft_status === "rejected" || event.draft_status === "failed" ? "pill danger" : event.draft_status === "posted" ? "pill" : "pill warn"}>
                  {DRAFT_STATUS_LABELS[event.draft_status] ?? event.draft_status}
                </span>
                {event.draft_id && (event.draft_status === "draft" || event.draft_status === "approved") ? (
                  <Link href={`/drafts?draftId=${event.draft_id}`} className="source-link">Review Draft →</Link>
                ) : null}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
