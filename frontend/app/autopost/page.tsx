import { AccessDenied } from "@/components/access-denied";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { AutopostDashboardPanel } from "@/components/autopost-dashboard-panel";
import { AutopostSetupPanel } from "@/components/autopost-setup-panel";
import { ShellHeader } from "@/components/shell-header";
import { getAutopostDashboard } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";

export default async function AutopostPage() {
  const { viewer, accessToken } = await requireServerViewer();
  if (viewer.role !== "customer") {
    return <AccessDenied title="Autopost" description="This simple autopost surface is only available in the customer workspace." />;
  }

  let dashboard;
  try {
    dashboard = await getAutopostDashboard(accessToken);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          eyebrow="Autopost"
          title="Your autopost workspace"
          description="Choose your news product, connect X, and let Newsbot handle the daily posting flow for you."
          viewer={viewer}
          freshnessLabel="Live customer autopost"
        />
        <AdminApiErrorPanel
          title="Autopost unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Customer Autopost"
        title="Your autopost workspace"
        description="Track your live posting flow, see what is scheduled next, and keep your feed clear without digging through operator detail."
        viewer={viewer}
        freshnessLabel="Live customer autopost"
      />
      {dashboard.status === "setup_required" ? (
        <AutopostSetupPanel
          displayName={dashboard.display_name}
          wireProduct={dashboard.wire_product}
          xConnected={dashboard.x_connected}
          openaiConfigured={dashboard.openai_configured}
          tavilyConfigured={dashboard.tavily_configured}
        />
      ) : (
        <AutopostDashboardPanel initialDashboard={dashboard} />
      )}
    </div>
  );
}
