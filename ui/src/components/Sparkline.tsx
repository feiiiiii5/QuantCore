export interface SparklineProps {
  values: number[];
  positive?: boolean;
  tone?: "up" | "down" | "auto";
  height?: number;
  area?: boolean;
  className?: string;
  ariaLabel?: string;
}

/** Inline mini trend line; colour comes from the --up/--down tokens only. */
export default function Sparkline({ values, positive, tone = "auto", height = 32, area, className, ariaLabel }: SparklineProps) {
  if (!values.length) return <span className="muted">—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pointList = values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * 100;
    const y = 30 - ((value - min) / span) * 26;
    return `${x},${y}`;
  });
  const direction = tone === "auto" ? (positive ?? values[values.length - 1] >= values[0]) : tone === "up";
  const stroke = direction ? "var(--up)" : "var(--down)";
  return (
    <svg
      viewBox="0 0 100 32"
      className={className ? `sparkline ${className}` : "sparkline"}
      style={{ height }}
      preserveAspectRatio="none"
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
    >
      {area ? <polygon points={`0,32 ${pointList.join(" ")} 100,32`} fill={stroke} opacity="0.12" /> : null}
      <polyline points={pointList.join(" ")} fill="none" stroke={stroke} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
