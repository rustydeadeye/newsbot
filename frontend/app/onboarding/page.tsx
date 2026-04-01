import { redirect } from "next/navigation";

import { CustomerDegradedState } from "@/components/customer-degraded-state";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { ShellHeader } from "@/components/shell-header";
import { getRoleHomePath, IS_AUTOPOST_MODE } from "@/lib/product-mode";
import { requireWorkspaceSession } from "@/lib/viewer";

export default async function OnboardingPage() {
  const { viewer, onboarding, onboardingError } = await requireWorkspaceSession();
  if (viewer.role !== "customer") {
    redirect("/");
  }
  if (IS_AUTOPOST_MODE) {
    redirect(getRoleHomePath("customer"));
  }
  if (onboardingError) {
    return (
      <div className="page-grid">
        <ShellHeader
          title="Welcome"
          description="Set up your customer workspace once so Newsbot can generate drafts that match your profile."
          viewer={viewer}
          freshnessLabel="Required first-run setup"
        />
        <CustomerDegradedState
          title="We could not load your onboarding steps"
          description="Newsbot had trouble opening your setup flow. Please try again shortly."
        />
      </div>
    );
  }
  if (onboarding?.onboarding_completed) {
    redirect("/");
  }

  return (
    <div className="page-grid">
      <ShellHeader
        eyebrow="Customer Setup"
        title="Welcome"
        description="Set up your workspace in a few short steps so Newsbot can generate your first drafts with the right voice and priorities."
        viewer={viewer}
        freshnessLabel="Required first-run setup"
      />
      <div className="onboarding-layout">
        <div className="guide-panel onboarding-intro">
          <div className="eyebrow">What you are setting up</div>
          <div className="section-hero-title">From sign-in to first draft</div>
          <p className="card-subtle">
            This setup takes a minute or two. Once it is complete, you will land in your workspace and can generate drafts from the latest updates right away.
          </p>
          <div className="workspace-list">
            <div className="workspace-list-row">
              <span>Profile</span>
              <strong>Choose your display name and default voice</strong>
            </div>
            <div className="workspace-list-row">
              <span>OpenAI</span>
              <strong>Unlock draft generation for your workspace</strong>
            </div>
            <div className="workspace-list-row">
              <span>X connection</span>
              <strong>Optional now, useful later for publishing</strong>
            </div>
          </div>
        </div>
        {onboarding ? <OnboardingWizard status={onboarding} /> : null}
      </div>
    </div>
  );
}
