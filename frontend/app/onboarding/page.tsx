import { redirect } from "next/navigation";

import { AccessDenied } from "@/components/access-denied";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { AutopostSetupPanel } from "@/components/autopost-setup-panel";
import { ShellHeader } from "@/components/shell-header";
import { getAutopostDashboard } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function OnboardingPage() {
  const { viewer, accessToken } = await requireServerViewer();
  if (viewer.role !== "customer") {
    return <AccessDenied title="Onboarding" description="This setup flow is only available in the customer workspace." />;
  }

  let dashboard;
  try {
    dashboard = await getAutopostDashboard(accessToken);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          eyebrow="Setup"
          title="Finish your setup"
          description="Connect your tools and choose your product before Newsbot starts publishing."
          viewer={viewer}
          freshnessLabel="Customer onboarding"
        />
        <AdminApiErrorPanel
          title="Onboarding unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  if (dashboard.status !== "setup_required") {
    redirect("/dashboard");
  }

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Setup"
        title="Finish your setup"
        description="Choose your news product, connect X, and add the tools Newsbot needs before you start autoposting."
        viewer={viewer}
        freshnessLabel="Customer onboarding"
      />
      <AutopostSetupPanel
        displayName={dashboard.display_name}
        wireProduct={dashboard.wire_product}
        xConnected={dashboard.x_connected}
        openaiConfigured={dashboard.openai_configured}
        tavilyConfigured={dashboard.tavily_configured}
      />
    </div>
  );
}
