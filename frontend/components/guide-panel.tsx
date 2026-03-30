export function GuidePanel({
  eyebrow,
  title,
  description,
  children
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="guide-panel">
      {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
      <div className="section-hero-title">{title}</div>
      <p className="card-subtle">{description}</p>
      {children ? <div className="stack">{children}</div> : null}
    </div>
  );
}
