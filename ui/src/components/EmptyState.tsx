import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

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
  const classes = ["empty-state"];
  if (compact) classes.push("compact");
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")}>
      <Icon size={22} className="empty-state-icon" aria-hidden="true" />
      {title ? <strong className="empty-state-title">{title}</strong> : null}
      {hint ? <span className="empty-state-hint">{hint}</span> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}
