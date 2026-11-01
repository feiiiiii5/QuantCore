export default function Sparkline({ values, positive }: { values: number[]; positive: boolean }) {
  if (!values.length) return <span className="muted">—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => `${(i / Math.max(values.length - 1, 1)) * 100},${30 - ((v - min) / span) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 100 32" className="sparkline" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" stroke={positive ? "var(--up)" : "var(--down)"} strokeWidth="1.8" />
    </svg>
  );
}
