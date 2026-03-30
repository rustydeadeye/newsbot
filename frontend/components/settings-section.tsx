export function SettingsSection({
  eyebrow,
  title,
  description,
  children
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="settings-section">
      {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
      <div className="settings-section-head">
        <div className="section-hero-title">{title}</div>
        {description ? <p className="card-subtle">{description}</p> : null}
      </div>
      <div className="settings-section-body">{children}</div>
    </section>
  );
}
