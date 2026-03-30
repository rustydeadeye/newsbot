import { ViewerProfile } from "@/lib/session";

export function ShellHeader({
  eyebrow,
  title,
  description,
  viewer,
  freshnessLabel,
  actions
}: {
  eyebrow?: string;
  title: string;
  description: string;
  viewer: ViewerProfile;
  freshnessLabel?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="shell-header">
      <div className="shell-header-copy">
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      <div className="shell-header-side">
        <div className="workspace-chip">
          <span className="status-dot" />
          <span>{viewer.role === "admin" ? "Admin workspace" : "Customer workspace"}</span>
        </div>
        <div className="workspace-subtle">
          <strong>{viewer.display_name ?? viewer.email}</strong>
          <span>{freshnessLabel ?? "Live workspace"}</span>
        </div>
        {actions ? <div className="inline-actions">{actions}</div> : null}
      </div>
    </div>
  );
}
