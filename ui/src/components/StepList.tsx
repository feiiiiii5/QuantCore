import type { ReactNode } from "react";
import { Check } from "lucide-react";

export interface StepListItem {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  done?: boolean;
  active?: boolean;
  actionLabel?: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}

export interface StepListProps {
  steps: StepListItem[];
  current?: number;
  onAction?: (id: string) => void;
  compact?: boolean;
  className?: string;
}

/** Beginner checklist / wizard steps with optional per-step CTA. */
export default function StepList({ steps, current, onAction, compact, className }: StepListProps) {
  const classes = ["step-list"];
  if (compact) classes.push("compact");
  if (className) classes.push(className);
  return (
    <ol className={classes.join(" ")}>
      {steps.map((step, index) => {
        const active = step.active ?? (current != null ? index === current : false);
        const itemClasses = ["step-item"];
        if (step.done) itemClasses.push("done");
        if (active) itemClasses.push("active");
        return (
          <li key={step.id} className={itemClasses.join(" ")}>
            <span className="step-index" aria-hidden="true">{step.done ? <Check size={12} /> : index + 1}</span>
            <div className="step-main">
              <div className="step-title">{step.title}</div>
              {step.description ? <div className="step-desc">{step.description}</div> : null}
              {step.hint ? <div className="step-desc muted">{step.hint}</div> : null}
            </div>
            {onAction && step.actionLabel ? (
              <div className="step-action">
                <button className="btn sm" disabled={step.disabled} onClick={() => onAction(step.id)}>{step.actionLabel}</button>
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
