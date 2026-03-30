import { ApiErrorPanel } from "@/components/api-error-panel";
import { PageHeader } from "@/components/page-header";
import { getEvents } from "@/lib/api";

export default async function EventsPage() {
  let events;
  try {
    events = await getEvents();
  } catch (error) {
    return (
      <div className="page-grid">
        <PageHeader title="Events" description="Normalized source events after dedupe, scoring, and fact extraction." />
        <ApiErrorPanel
          title="Events feed unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
      <PageHeader title="Events" description="Normalized source events after dedupe, scoring, and fact extraction." />
      <div className="card-grid">
        {events.map((event) => (
          <div key={event.id} className="card">
            <div className="row space">
              <span className="pill">{event.event_type}</span>
              <span className="mono">{event.ticker ?? "MARKET"}</span>
            </div>
            <div className="headline">{String(event.summary_facts.headline ?? event.entity_name ?? event.event_type)}</div>
            <div className="card-subtle">
              {String(event.summary_facts.source_name ?? "unknown")} | score {event.importance_score} | confidence{" "}
              {event.confidence_score}
            </div>
            <div className="mono" style={{ marginTop: 12 }}>{event.dedupe_key}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
