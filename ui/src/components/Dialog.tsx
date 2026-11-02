import type { ReactNode } from "react";
import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import clsx from "clsx";

export type DialogSize = "sm" | "md" | "lg" | "xl";

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  size?: DialogSize;
  className?: string;
  hideClose?: boolean;
  closeLabel?: string;
  children?: ReactNode;
}

/** Radix dialog with Apple sheet material and scale-in motion (reduced-motion aware). */
export default function Dialog({
  open, onOpenChange, title, description, footer, size = "md", className, hideClose, closeLabel = "关闭", children,
}: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="dialog-overlay" />
        <RadixDialog.Content className={clsx("dialog-panel", className)} data-size={size}>
          <div className="dialog-head">
            <RadixDialog.Title className="dialog-title">{title}</RadixDialog.Title>
            {hideClose ? null : (
              <RadixDialog.Close asChild>
                <button type="button" className="icon-btn" aria-label={closeLabel}><X size={18} /></button>
              </RadixDialog.Close>
            )}
          </div>
          {description != null ? <RadixDialog.Description className="dialog-desc">{description}</RadixDialog.Description> : null}
          <div className="dialog-body">{children}</div>
          {footer != null ? <div className="dialog-foot">{footer}</div> : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
