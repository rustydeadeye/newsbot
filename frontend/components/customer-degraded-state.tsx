export function CustomerDegradedState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="panel degraded-state">
      <div className="section-title">Temporary issue</div>
      <div className="headline">{title}</div>
      <p className="card-subtle">{description}</p>
    </div>
  );
}
