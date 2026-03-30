export function EmptyState({
  title,
  description,
  action
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel empty-state">
      <div className="headline">{title}</div>
      <p className="card-subtle">{description}</p>
      {action ? <div className="inline-actions">{action}</div> : null}
    </div>
  );
}
