import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Tone } from "./Badge";

export interface MetricPillProps {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
  className?: string;
}

/** Compact inline metric (result pages / confidence badges). */
export default function MetricPill({ label, value, hint, tone = "neutral", icon: Icon, className }: MetricPillProps) {
  const classes = ["metric-pill"];
  if (tone !== "neutral") classes.push(`tone-${tone}`);
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")}>
      <div className="metric-pill-label">
        {Icon ? <Icon size={12} aria-hidden="true" /> : null}
        <span>{label}</span>
      </div>
      <div className="metric-pill-value">{value}</div>
      {hint != null ? <div className="metric-pill-hint">{hint}</div> : null}
    </div>
  );
}
