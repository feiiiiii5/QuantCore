import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export interface TabItem {
  id: string;
  label: ReactNode;
  badge?: ReactNode;
  icon?: LucideIcon;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel?: string;
  variant?: "line" | "pill";
  className?: string;
}

/** Secondary navigation tabs (backtest result tabs, research tabs…). */
export default function Tabs({ items, value, onChange, ariaLabel, variant = "line", className }: TabsProps) {
  const classes = ["tabs"];
  if (variant === "pill") classes.push("pill");
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === value}
            className={item.id === value ? "tab active" : "tab"}
            disabled={item.disabled}
            onClick={() => onChange(item.id)}
          >
            {Icon ? <Icon size={14} aria-hidden="true" /> : null}
            {item.label}
            {item.badge ? <span className="badge tone-neutral">{item.badge}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
