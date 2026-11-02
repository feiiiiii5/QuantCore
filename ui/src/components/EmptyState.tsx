import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";
import clsx from "clsx";

export interface EmptyStateProps {
  title?: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  icon?: LucideIcon;
  compact?: boolean;
  className?: string;
}

/** Empty state: what happened, why, and the next action. */
export default function EmptyState({ title, hint, action, icon: Icon = Inbox, compact, className }: EmptyStateProps) {
  return (
    <div className={clsx("empty", compact && "compact", className)}>
      <Icon size={22} className="empty-icon" aria-hidden="true" />
      {title != null ? <strong className="empty-title">{title}</strong> : null}
      {hint != null ? <span className="empty-hint">{hint}</span> : null}
      {action != null ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}
