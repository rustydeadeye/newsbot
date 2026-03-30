import { redirect } from "next/navigation";

import { AuthForm } from "@/components/auth-form";
import { getServerViewer } from "@/lib/viewer";

export default async function LoginPage() {
  const viewer = await getServerViewer();
  if (viewer) {
    redirect("/");
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-hero">
          <div className="eyebrow">Newsbot Command Center</div>
          <h1>Sign in to your workspace</h1>
          <p className="card-subtle">
            Review live news, guide the draft pipeline, and access the controls that match your role in the workspace.
          </p>
        </div>
        <div className="auth-benefits">
          <div className="workspace-list-row">
            <span>Customer access</span>
            <strong>Review and refine content quickly</strong>
          </div>
          <div className="workspace-list-row">
            <span>Admin access</span>
            <strong>Monitor publishing and source health</strong>
          </div>
        </div>
        <AuthForm />
      </div>
    </div>
  );
}
