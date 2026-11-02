import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Tone } from "./Badge";

export interface StatTileProps {
  label: ReactNode;
  value: ReactNode;
  delta?: ReactNode;
  trend?: "up" | "down" | "flat";
  hint?: ReactNode;
  tone?: Tone;
  size?: "sm" | "md" | "lg";
  icon?: LucideIcon;
  className?: string;
}

/** One key number with label/delta/hint; values use tabular numerals. */
export default function StatTile({
  label, value, delta, trend, hint, tone = "neutral", size = "md", icon: Icon, className,
}: StatTileProps) {
  const classes = ["stat-tile"];
  if (size !== "md") classes.push(size);
  if (tone !== "neutral") classes.push(`tone-${tone}`);
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")}>
      <div className="stat-tile-label">
        {Icon ? <Icon size={13} aria-hidden="true" /> : null}
        <span>{label}</span>
      </div>
      <div className="stat-tile-value">{value}</div>
      {delta != null ? <div className={`stat-tile-delta${trend ? ` trend-${trend}` : ""}`}>{delta}</div> : null}
      {hint != null ? <div className="stat-tile-hint">{hint}</div> : null}
    </div>
  );
}
