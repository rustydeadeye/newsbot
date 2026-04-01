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
          title="Autopost"
          description="Connect X, turn autoposting on, and let Newsbot handle the ongoing posting flow."
          viewer={viewer}
          freshnessLabel="Simple wire-feed customer surface"
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
        title="Autopost"
        description="This branch keeps your posting flow simple: connect X, turn autoposting on, and follow what goes out next."
        viewer={viewer}
        freshnessLabel="Simple wire-feed customer surface"
      />
      {dashboard.status === "setup_required" ? (
        <AutopostSetupPanel displayName={dashboard.display_name} xConnected={dashboard.x_connected} />
      ) : (
        <AutopostDashboardPanel initialDashboard={dashboard} />
      )}
    </div>
  );
}
