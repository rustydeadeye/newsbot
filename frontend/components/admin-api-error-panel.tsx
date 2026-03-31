export function AdminApiErrorPanel({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="panel">
      <div className="headline">{title}</div>
      <div className="card-subtle">{detail}</div>
      <div className="card-subtle" style={{ marginTop: 12 }}>
        Check that the backend is healthy and that <code>NEXT_PUBLIC_API_BASE_URL</code> points to the deployed API.
      </div>
    </div>
  );
}
