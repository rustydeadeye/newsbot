import { ApiErrorPanel } from "@/components/api-error-panel";
import { SettingsForm } from "@/components/settings-form";
import { SettingsSection } from "@/components/settings-section";
import { ShellHeader } from "@/components/shell-header";
import { StatusPanel } from "@/components/status-panel";
import { getCreatorSettings, getSources } from "@/lib/api";
import { CreatorSettings, SourceSummary } from "@/lib/types";
import { requireServerViewer } from "@/lib/viewer";

export default async function SettingsPage() {
  const { viewer, accessToken } = await requireServerViewer();
  const role = viewer.role;
  let sources: SourceSummary[] = [];
  let settings: CreatorSettings;
  try {
    if (role === "admin") {
      [sources, settings] = await Promise.all([getSources(accessToken), getCreatorSettings(accessToken)]);
    } else {
      settings = await getCreatorSettings(accessToken);
    }
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Settings"
          description="Manage the controls that shape how Newsbot works for you."
          viewer={viewer}
          freshnessLabel="Workspace configuration"
        />
        <ApiErrorPanel
          title="Settings unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Workspace Settings"
        title="Settings"
        description={
          role === "admin"
            ? "Manage both customer-facing controls and the system settings that affect coverage and delivery."
            : "Manage your workspace preferences, watchlist, and content guardrails."
        }
        viewer={viewer}
        freshnessLabel={role === "admin" ? "Customer-owned and system-owned controls" : "Customer-owned controls"}
      />
      <div className="settings-layout">
        <SettingsSection
          eyebrow="Customer-owned controls"
          title={role === "admin" ? "Workspace preferences visible to customers" : "My workspace preferences"}
          description="These settings shape what gets surfaced, how drafts are framed, and how the workspace feels day to day."
        >
          <SettingsForm settings={settings} role={role} />
        </SettingsSection>
        {role === "admin" ? (
          <SettingsSection
            eyebrow="System-owned controls"
            title="Source readiness and operational coverage"
            description="These controls stay admin-only because they affect ingestion, monitoring, and delivery confidence."
          >
            <StatusPanel
              eyebrow="Source coverage"
              title="Monitor source readiness"
              description="Use this list to spot disabled sources before they create silent coverage gaps."
              tone={sources.some((source) => !source.enabled) ? "warning" : "default"}
            />
            <div className="stack">
              {sources.map((source) => (
                <div key={source.id} className="row space source-row">
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
          </SettingsSection>
        ) : (
          <StatusPanel
            eyebrow="How settings work"
            title="These controls shape what you review"
            description="Your watchlist and blocked phrases change what gets surfaced and how drafts are framed, but they do not expose system-level publishing controls."
          />
        )}
      </div>
    </div>
  );
}
