import type { ReactNode } from "react";
import * as RadixDialog from "@radix-ui/react-dialog";
import { Drawer } from "vaul";
import { X } from "lucide-react";
import clsx from "clsx";

export type SheetSide = "right" | "bottom";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  side?: SheetSide;
  title?: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
  closeLabel?: string;
  children?: ReactNode;
}

function SheetHead({ title, description, onClose, closeLabel }: { title?: ReactNode; description?: ReactNode; onClose: () => void; closeLabel: string }) {
  return (
    <div className="sheet-head">
      <div style={{ minWidth: 0 }}>
        {title != null ? <div className="sheet-title">{title}</div> : null}
        {description != null ? <div className="sheet-desc">{description}</div> : null}
      </div>
      <button type="button" className="icon-btn" aria-label={closeLabel} onClick={onClose}><X size={18} /></button>
    </div>
  );
}

/**
 * Side sheet on desktop (Radix dialog) and iOS-style bottom drawer on mobile (vaul).
 * Both variants share the same header/body/footer slots.
 */
export default function Sheet({
  open, onOpenChange, side = "right", title, description, footer, size = "md", className, closeLabel = "关闭", children,
}: SheetProps) {
  if (side === "bottom") {
    return (
      <Drawer.Root open={open} onOpenChange={onOpenChange}>
        <Drawer.Portal>
          <Drawer.Overlay className="sheet-overlay" />
          <Drawer.Content className={clsx("sheet-panel", className)} data-side="bottom" aria-describedby={undefined}>
            <div className="sheet-grabber" aria-hidden="true" />
            <Drawer.Title className="sr-only">{typeof title === "string" ? title : "面板"}</Drawer.Title>
            {description != null ? <Drawer.Description className="sr-only">{typeof description === "string" ? description : "面板说明"}</Drawer.Description> : null}
            <SheetHead title={title} description={description} onClose={() => onOpenChange(false)} closeLabel={closeLabel} />
            <div className="sheet-body">{children}</div>
            {footer != null ? <div className="sheet-foot">{footer}</div> : null}
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    );
  }
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="sheet-overlay" />
        <RadixDialog.Content className={clsx("sheet-panel", className)} data-side="right" data-size={size}>
          <RadixDialog.Title className="sr-only">{title ?? "面板"}</RadixDialog.Title>
          {description != null ? <RadixDialog.Description className="sr-only">{description}</RadixDialog.Description> : null}
          <SheetHead title={title} description={description} onClose={() => onOpenChange(false)} closeLabel={closeLabel} />
          <div className="sheet-body">{children}</div>
          {footer != null ? <div className="sheet-foot">{footer}</div> : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
