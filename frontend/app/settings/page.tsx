import { ApiErrorPanel } from "@/components/api-error-panel";
import { SettingsForm } from "@/components/settings-form";
import { PageHeader } from "@/components/page-header";
import { getCreatorSettings, getSources } from "@/lib/api";

export default async function SettingsPage() {
  let sources;
  let settings;
  try {
    [sources, settings] = await Promise.all([getSources(), getCreatorSettings()]);
  } catch (error) {
    return (
      <div className="page-grid">
        <PageHeader title="Settings" description="Current source inventory and baseline operating setup." />
        <ApiErrorPanel
          title="Settings unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
      <PageHeader title="Settings" description="Current source inventory and baseline operating setup." />
      <div className="card-grid">
        <div className="card">
          <div className="headline">Source Coverage</div>
          <div className="stack">
            {sources.map((source) => (
              <div key={source.id} className="row space">
                <div>
                  <div>{source.name}</div>
                  <div className="card-subtle">
                    {source.type} | poll {source.poll_interval_sec}s
                  </div>
                </div>
                <span className={source.enabled ? "pill" : "pill danger"}>{source.enabled ? "enabled" : "disabled"}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="headline">Creator Controls</div>
          <SettingsForm settings={settings} />
        </div>
      </div>
    </div>
  );
}
