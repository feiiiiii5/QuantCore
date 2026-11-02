import type { ReactNode } from "react";
import * as RadixPopover from "@radix-ui/react-popover";
import clsx from "clsx";

export interface PopoverProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "center" | "end";
  side?: "top" | "right" | "bottom" | "left";
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

/** Radix popover for filters, quick settings and date pickers. */
export default function Popover({ trigger, children, align = "start", side = "bottom", open, onOpenChange, className }: PopoverProps) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content className={clsx("popover-content", className)} align={align} side={side} sideOffset={6} collisionPadding={12}>
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
