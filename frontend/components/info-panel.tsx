export function InfoPanel({
  eyebrow,
  title,
  description,
  children,
  tone = "default"
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: React.ReactNode;
  tone?: "default" | "warning";
}) {
  return (
    <div className={tone === "warning" ? "panel info-panel warning" : "panel info-panel"}>
      {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
      <div className="section-hero-title">{title}</div>
      <p className="card-subtle">{description}</p>
      {children ? <div className="stack">{children}</div> : null}
    </div>
  );
}
