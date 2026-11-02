import type { ReactNode } from "react";
import * as RadixTabs from "@radix-ui/react-tabs";
import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

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

/** Radix tabs list; panels stay in the page (hidden/shown by the consumer). */
export default function Tabs({ items, value, onChange, ariaLabel, variant = "line", className }: TabsProps) {
  return (
    <RadixTabs.Root value={value} onValueChange={onChange}>
      <RadixTabs.List
        className={clsx("tabs", variant === "pill" && "pill", className)}
        aria-label={ariaLabel}
      >
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <RadixTabs.Trigger key={item.id} value={item.id} className="tab" disabled={item.disabled}>
              {Icon ? <Icon size={15} aria-hidden="true" /> : null}
              {item.label}
              {item.badge != null ? <span className="badge badge-neutral">{item.badge}</span> : null}
            </RadixTabs.Trigger>
          );
        })}
      </RadixTabs.List>
    </RadixTabs.Root>
  );
}
