export function MetricCard({ label, value, tone = "neutral", hint }: { label: string; value: string; tone?: "neutral" | "up" | "down"; hint?: string }) {
  return (
    <div className="card metric-card">
      <h3>{label}</h3>
      <div className={`kpi ${tone}`}>{value}</div>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}
