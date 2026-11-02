import type { ReactNode } from "react";

export type Tone = "neutral" | "ok" | "warn" | "danger" | "info" | "up" | "down";

export interface BadgeProps {
  tone?: Tone;
  dot?: boolean;
  title?: string;
  children: ReactNode;
  className?: string;
}

/** Compact status badge; tone maps to semantic tokens only. */
export function Badge({ tone = "neutral", dot, title, children, className }: BadgeProps) {
  const classes = ["badge", `tone-${tone}`];
  if (className) classes.push(className);
  return (
    <span className={classes.join(" ")} title={title}>
      {dot ? <span className="badge-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export interface TagProps {
  tone?: Tone;
  active?: boolean;
  onClick?: () => void;
  onRemove?: () => void;
  children: ReactNode;
  className?: string;
  title?: string;
}

/** Filter chip / removable tag. */
export function Tag({ tone = "neutral", active, onClick, onRemove, children, className, title }: TagProps) {
  const classes = ["tag"];
  if (active) classes.push("active");
  if (className) classes.push(className);
  const content = (
    <>
      {children}
      {onRemove ? (
        <button type="button" className="tag-remove" aria-label="移除" onClick={(event) => { event.stopPropagation(); onRemove(); }}>
          ×
        </button>
      ) : null}
    </>
  );
  if (!onClick) return <span className={classes.join(" ")} data-tone={tone} title={title}>{content}</span>;
  return (
    <button type="button" className={classes.join(" ")} data-tone={tone} title={title} onClick={onClick} aria-pressed={active}>
      {content}
    </button>
  );
}

export default Badge;
