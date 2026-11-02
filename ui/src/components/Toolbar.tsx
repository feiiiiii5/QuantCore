import type { ReactNode } from "react";

export interface ToolbarProps {
  children?: ReactNode;
  actions?: ReactNode;
  sticky?: boolean;
  className?: string;
}

/** In-page filter/action bar. */
export default function Toolbar({ children, actions, sticky, className }: ToolbarProps) {
  const classes = ["toolbar"];
  if (sticky) classes.push("sticky");
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")} role="toolbar">
      {children}
      {actions ? <><span className="spacer" /><div className="row">{actions}</div></> : null}
    </div>
  );
}
