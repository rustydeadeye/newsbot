import { redirect } from "next/navigation";

import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { ConnectXButton } from "@/components/connect-x-button";
import { CustomerDegradedState } from "@/components/customer-degraded-state";
import { SettingsForm } from "@/components/settings-form";
import { SettingsSection } from "@/components/settings-section";
import { ShellHeader } from "@/components/shell-header";
import { SourceToggle } from "@/components/source-toggle";
import { StatusPanel } from "@/components/status-panel";
import { getCreatorSettings, getSources } from "@/lib/api";
import { CreatorSettings, SourceSummary } from "@/lib/types";
import { requireWorkspaceSession } from "@/lib/viewer";

export default async function SettingsPage() {
  const { viewer, accessToken, onboarding, onboardingError } = await requireWorkspaceSession();
  const role = viewer.role;
  if (role === "customer" && onboardingError) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Settings"
          description="Manage the controls that shape how Newsbot works for you."
          viewer={viewer}
          freshnessLabel="Workspace configuration"
        />
        <CustomerDegradedState
          title="We could not finish loading your settings"
          description="Newsbot had trouble loading your customer setup. Please try again shortly."
        />
      </div>
    );
  }
  if (role === "customer" && onboarding && !onboarding.onboarding_completed) {
    redirect("/onboarding");
  }
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
        {role === "admin" ? (
          <AdminApiErrorPanel
            title="Settings unavailable"
            detail={error instanceof Error ? error.message : "Unknown API error"}
          />
        ) : (
          <CustomerDegradedState
            title="We could not load your settings right now"
            description="Newsbot had trouble opening your workspace settings. Please try again shortly."
          />
        )}
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
        {role === "admin" ? (
          <SettingsSection
            eyebrow="Customer-owned controls"
            title="Workspace preferences visible to customers"
            description="These settings shape what gets surfaced, how drafts are framed, and how the workspace feels day to day."
          >
            <SettingsForm settings={settings} role={role} />
          </SettingsSection>
        ) : (
          <>
            <SettingsSection
              eyebrow="Profile"
              title="How Newsbot presents your workspace"
              description="Set the name and voice Newsbot should use when framing draft copy for you."
            >
              <SettingsForm settings={settings} role={role} section="profile" />
            </SettingsSection>
            <SettingsSection
              eyebrow="Draft generation"
              title="AI drafting connection"
              description="Connect or replace your OpenAI key so Newsbot can generate draft copy for your workspace."
            >
              <SettingsForm settings={settings} role={role} section="generation" />
            </SettingsSection>
            <SettingsSection
              eyebrow="Content filters"
              title="What should be prioritized or avoided"
              description="Use your watchlist and phrase filters to shape which updates rise to the top and how the draft is worded."
            >
              <SettingsForm settings={settings} role={role} section="filters" />
            </SettingsSection>
            <SettingsSection
              eyebrow="Automation"
              title="How Newsbot should work while you are away"
              description="Choose whether drafts should be generated automatically, how long they stay fresh, and whether macro/regulatory items may auto-post."
            >
              <SettingsForm settings={settings} role={role} section="automation" />
            </SettingsSection>
            <SettingsSection
              eyebrow="Publishing connection"
              title="Connect X when you are ready"
              description="X is only needed for publishing workflows. You can review and generate drafts without connecting it."
            >
              <ConnectXButton connected={settings.x_connected} nextPath="/settings" />
            </SettingsSection>
            <StatusPanel
              eyebrow="How settings work"
              title="These controls shape what you review"
              description="Newsbot uses your preferences to prioritize updates, draft the wording, and keep unwanted phrases out of customer-facing copy."
            />
          </>
        )}
        {role === "admin" ? (
          <SettingsSection
            eyebrow="Publishing account"
            title="X (Twitter) account"
            description="Connect the X account that Newsbot will post from. Tokens are stored securely and refreshed automatically."
          >
            <ConnectXButton connected={settings.x_connected} nextPath="/settings" />
          </SettingsSection>
        ) : null}
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
                <SourceToggle key={source.id} source={source} />
              ))}
            </div>
          </SettingsSection>
        ) : null}
      </div>
    </div>
  );
}
