export function PageHeader({
  title,
  description,
  side
}: {
  title: string;
  description: string;
  side?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {side}
    </div>
  );
}
