import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, CheckCircle2, Info, OctagonAlert } from "lucide-react";
import clsx from "clsx";

export type CalloutTone = "info" | "warn" | "danger" | "success";

export interface CalloutProps {
  tone?: CalloutTone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  icon?: LucideIcon;
  className?: string;
}

const DEFAULT_ICONS: Record<CalloutTone, LucideIcon> = {
  info: Info,
  warn: AlertTriangle,
  danger: OctagonAlert,
  success: CheckCircle2,
};

/** Inline status message with tone icon (DESIGN-SPEC §4.1). */
export default function Callout({ tone = "info", title, children, action, icon, className }: CalloutProps) {
  const Icon = icon ?? DEFAULT_ICONS[tone];
  return (
    <div className={clsx("callout", `callout-${tone}`, className)} role={tone === "danger" ? "alert" : undefined}>
      <span className="callout-icon"><Icon size={16} aria-hidden="true" /></span>
      <div className="callout-main">
        {title != null ? <div className="callout-title">{title}</div> : null}
        {children}
      </div>
      {action != null ? <div className="callout-action">{action}</div> : null}
    </div>
  );
}
