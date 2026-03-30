export function KpiCard({
  label,
  value,
  detail,
  tone = "default"
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: "default" | "warning" | "danger" | "calm";
}) {
  return (
    <div className={`kpi-card${tone === "default" ? "" : ` ${tone}`}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {detail ? <div className="card-subtle">{detail}</div> : null}
    </div>
  );
}
