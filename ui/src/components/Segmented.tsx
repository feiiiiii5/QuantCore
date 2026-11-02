import type { ReactNode } from "react";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export interface SegmentedOption {
  value: string;
  label: ReactNode;
  hint?: string;
  icon?: LucideIcon;
  disabled?: boolean;
}

/** v2 alias kept for pages that describe the same item shape as `items`. */
export type SegmentedItem = SegmentedOption;

export interface SegmentedProps {
  /** v2 preferred list of items. */
  items?: SegmentedOption[];
  /** v1 compatibility alias (Market/Paper/Strategy pages still pass this). */
  options?: SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
  size?: "sm" | "md";
  ariaLabel?: string;
  className?: string;
}

/** Radix single-select toggle group (Apple segmented control). */
export default function Segmented({ items, options, value, onChange, size = "md", ariaLabel, className }: SegmentedProps) {
  const list = items ?? options ?? [];
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(next) => { if (next) onChange(next); }}
      className={clsx("segmented", size === "sm" && "segmented-sm", className)}
      aria-label={ariaLabel}
      disabled={false}
    >
      {list.map((item) => {
        const Icon = item.icon;
        return (
          <ToggleGroup.Item
            key={item.value}
            value={item.value}
            className="segmented-item"
            disabled={item.disabled}
            title={item.hint}
          >
            {Icon ? <Icon size={14} aria-hidden="true" /> : null}
            {item.label}
          </ToggleGroup.Item>
        );
      })}
    </ToggleGroup.Root>
  );
}
