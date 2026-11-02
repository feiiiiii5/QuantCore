import type { ReactNode } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export type MenuItem =
  | { label: string; icon?: LucideIcon; danger?: boolean; disabled?: boolean; onSelect?: () => void; hint?: string }
  | { separator: true }
  | { label: string; heading: true };

export interface MenuProps {
  trigger: ReactNode;
  items: MenuItem[];
  align?: "start" | "center" | "end";
  side?: "top" | "bottom";
  className?: string;
}

function isSeparator(item: MenuItem): item is { separator: true } {
  return "separator" in item && item.separator === true;
}

function isHeading(item: MenuItem): item is { label: string; heading: true } {
  return "heading" in item && item.heading === true;
}

/** Radix dropdown menu for row-level actions. */
export default function Menu({ trigger, items, align = "end", side = "bottom", className }: MenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className={clsx("menu-content", className)} align={align} side={side} sideOffset={6} collisionPadding={12}>
          {items.map((item, index) => {
            if (isSeparator(item)) return <DropdownMenu.Separator key={`sep-${index}`} className="menu-sep" />;
            if (isHeading(item)) return <DropdownMenu.Label key={`label-${index}`} className="menu-label">{item.label}</DropdownMenu.Label>;
            const Icon = item.icon;
            return (
              <DropdownMenu.Item
                key={`item-${item.label}-${index}`}
                className={clsx("menu-item", item.danger && "danger")}
                disabled={item.disabled}
                onSelect={() => item.onSelect?.()}
              >
                {Icon ? <span className="menu-item-icon"><Icon size={15} aria-hidden="true" /></span> : null}
                <span className="menu-item-label">{item.label}</span>
                {item.hint ? <span className="menu-item-hint">{item.hint}</span> : null}
              </DropdownMenu.Item>
            );
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
