import type { CSSProperties, ReactNode } from "react";
import clsx from "clsx";

export type PanelTone = "neutral" | "ok" | "warn" | "danger" | "info";

export interface PanelProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  dense?: boolean;
  flush?: boolean;
  tone?: PanelTone;
  className?: string;
  bodyClassName?: string;
  id?: string;
  style?: CSSProperties;
  children?: ReactNode;
}

/** Surface card (v2 card contract): title/subtitle/actions head + body. */
export default function Panel({
  title, subtitle, actions, dense, flush, tone = "neutral", className, bodyClassName, id, style, children,
}: PanelProps) {
  return (
    <section
      className={clsx("card", dense && "dense", flush && "flush", tone !== "neutral" && `tone-${tone}`, className)}
      id={id}
      style={style}
    >
      {title != null || subtitle != null || actions != null ? (
        <header className="card-head">
          <div style={{ minWidth: 0 }}>
            {title != null ? <div className="card-title">{title}</div> : null}
            {subtitle != null ? <div className="card-sub">{subtitle}</div> : null}
          </div>
          {actions != null ? <div className="card-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={clsx("card-body", bodyClassName)}>{children}</div>
    </section>
  );
}
