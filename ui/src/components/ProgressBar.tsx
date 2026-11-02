import type { ReactNode } from "react";
import clsx from "clsx";

export type ProgressTone = "accent" | "ok" | "warn" | "danger";

export interface ProgressBarProps {
  /** 0–100. */
  value: number;
  tone?: ProgressTone;
  label?: ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
}

function clamp(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

/** Thin determinate progress bar (DESIGN-SPEC §4.1). */
export default function ProgressBar({ value, tone = "accent", label, size = "md", className }: ProgressBarProps) {
  const pct = clamp(value);
  return (
    <div className={clsx("progress", size, className)} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
      {label != null ? (
        <div className="progress-label">
          <span>{label}</span>
          <span className="tnum">{Math.round(pct)}%</span>
        </div>
      ) : null}
      <div className="progress-track">
        <div className={clsx("progress-fill", tone !== "accent" && tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
