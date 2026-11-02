import type { CSSProperties, ReactNode } from "react";

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

/** Generic surface card: title/subtitle/actions header + body. */
export default function Panel({
  title, subtitle, actions, dense, flush, tone = "neutral", className, bodyClassName, id, style, children,
}: PanelProps) {
  const classes = ["panel"];
  if (dense) classes.push("dense");
  if (flush) classes.push("flush");
  if (tone !== "neutral") classes.push(`tone-${tone}`);
  if (className) classes.push(className);
  return (
    <section className={classes.join(" ")} id={id} style={style}>
      {title || subtitle || actions ? (
        <header className="panel-head">
          <div className="panel-head-main">
            {title ? <h3 className="panel-title">{title}</h3> : null}
            {subtitle ? <div className="panel-subtitle">{subtitle}</div> : null}
          </div>
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={bodyClassName ? `panel-body ${bodyClassName}` : "panel-body"}>{children}</div>
    </section>
  );
}
