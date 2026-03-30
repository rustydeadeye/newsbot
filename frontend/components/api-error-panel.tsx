export function ApiErrorPanel({
  title,
  detail
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="panel">
      <div className="headline">{title}</div>
      <div className="card-subtle">
        {detail}
      </div>
      <div className="card-subtle" style={{ marginTop: 12 }}>
        Check that the FastAPI server is running and that `NEXT_PUBLIC_API_BASE_URL` points to it.
      </div>
    </div>
  );
}
