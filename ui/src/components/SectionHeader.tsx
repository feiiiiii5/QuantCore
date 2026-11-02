import type { ReactNode } from "react";

export interface SectionHeaderProps {
  title: ReactNode;
  hint?: ReactNode;
  actions?: ReactNode;
  level?: 2 | 3;
  className?: string;
}

/** Section title + one-line hint + right-aligned actions. */
export default function SectionHeader({ title, hint, actions, level = 2, className }: SectionHeaderProps) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div className={className ? `section-header ${className}` : "section-header"}>
      <div>
        <Heading>{title}</Heading>
        {hint ? <div className="section-header-hint">{hint}</div> : null}
      </div>
      {actions ? <div className="section-header-actions">{actions}</div> : null}
    </div>
  );
}
