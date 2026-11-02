import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export interface SegmentedOption {
  value: string;
  label: ReactNode;
  hint?: string;
  icon?: LucideIcon;
  disabled?: boolean;
}

export interface SegmentedProps {
  options: SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
  size?: "sm" | "md";
  ariaLabel?: string;
  className?: string;
}

/** Small mode switch (2–4 options). */
export default function Segmented({ options, value, onChange, size = "md", ariaLabel, className }: SegmentedProps) {
  const classes = ["segmented"];
  if (size === "sm") classes.push("sm");
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")} role="group" aria-label={ariaLabel}>
      {options.map((option) => {
        const Icon = option.icon;
        return (
          <button
            key={option.value}
            type="button"
            className={option.value === value ? "active" : ""}
            aria-pressed={option.value === value}
            title={option.hint}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
          >
            {Icon ? <Icon size={13} aria-hidden="true" /> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
