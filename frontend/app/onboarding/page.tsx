import { redirect } from "next/navigation";

import { OnboardingWizard } from "@/components/onboarding-wizard";
import { ShellHeader } from "@/components/shell-header";
import { requireWorkspaceSession } from "@/lib/viewer";

export default async function OnboardingPage() {
  const { viewer, onboarding } = await requireWorkspaceSession();
  if (viewer.role !== "customer") {
    redirect("/");
  }
  if (onboarding?.onboarding_completed) {
    redirect("/");
  }

  return (
    <div className="page-grid">
      <ShellHeader
        title="Welcome"
        description="Set up your customer workspace once so Newsbot can generate drafts that match your profile."
        viewer={viewer}
        freshnessLabel="Required first-run setup"
      />
      {onboarding ? <OnboardingWizard status={onboarding} /> : null}
    </div>
  );
}
