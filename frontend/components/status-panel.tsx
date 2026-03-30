export function StatusPanel({
  eyebrow,
  title,
  description,
  tone = "default",
  children
}: {
  eyebrow?: string;
  title: string;
  description: string;
  tone?: "default" | "warning" | "danger";
  children?: React.ReactNode;
}) {
  return (
    <div className={`status-panel${tone === "default" ? "" : ` ${tone}`}`}>
      {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
      <div className="section-hero-title">{title}</div>
      <p className="card-subtle">{description}</p>
      {children ? <div className="stack">{children}</div> : null}
    </div>
  );
}
