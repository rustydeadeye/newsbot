import { AccessDenied } from "@/components/access-denied";
import { AdminApiErrorPanel } from "@/components/admin-api-error-panel";
import { AutopostDashboardPanel } from "@/components/autopost-dashboard-panel";
import { ShellHeader } from "@/components/shell-header";
import { getAutopostDashboard } from "@/lib/api";
import { requireServerViewer } from "@/lib/viewer";
import { redirect } from "next/navigation";

export default async function DashboardPage() {
  const { viewer, accessToken } = await requireServerViewer();
  if (viewer.role !== "customer") {
    return <AccessDenied title="Dashboard" description="This customer dashboard is only available in the client workspace." />;
  }

  let dashboard;
  try {
    dashboard = await getAutopostDashboard(accessToken);
  } catch (error) {
    return (
      <div className="page-grid">
        <ShellHeader
          eyebrow="Customer Dashboard"
          title="Your dashboard"
          description="Choose your news product, connect X, and let Newsbot handle the daily posting flow for you."
          viewer={viewer}
          freshnessLabel="Live customer dashboard"
        />
        <AdminApiErrorPanel
          title="Dashboard unavailable"
          detail={error instanceof Error ? error.message : "Unknown API error"}
        />
      </div>
    );
  }

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Customer Dashboard"
        title="Your dashboard"
        description="Track your live posting flow, see what is scheduled next, and keep your feed clear without digging through operator detail."
        viewer={viewer}
        freshnessLabel="Live customer dashboard"
      />
      {dashboard.status === "setup_required" ? redirect("/onboarding") : <AutopostDashboardPanel initialDashboard={dashboard} />}
    </div>
  );
}
