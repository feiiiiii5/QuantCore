import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import clsx from "clsx";

export interface ListProps {
  children: ReactNode;
  className?: string;
  inset?: boolean;
  header?: ReactNode;
}

/** Apple grouped list container used on settings/data pages. */
export default function List({ children, className, inset, header }: ListProps) {
  return (
    <div className={clsx("list", inset && "inset", className)}>
      {header != null ? <div className="list-header">{header}</div> : null}
      {children}
    </div>
  );
}

export interface ListRowProps {
  title: ReactNode;
  subtitle?: ReactNode;
  leading?: ReactNode;
  trailing?: ReactNode;
  action?: ReactNode;
  onClick?: () => void;
  href?: string;
  selected?: boolean;
  danger?: boolean;
  disabled?: boolean;
  className?: string;
}

/** One grouped-list row: title/subtitle + leading icon + trailing accessory. */
export function ListRow({
  title, subtitle, leading, trailing, action, onClick, href, selected, danger, disabled, className,
}: ListRowProps) {
  const classes = clsx("list-row", selected && "selected", danger && "danger", className);
  const content = (
    <>
      {leading != null ? <span className="list-row-leading">{leading}</span> : null}
      <span className="list-row-main">
        <span className="list-row-title">{title}</span>
        {subtitle != null ? <span className="list-row-sub">{subtitle}</span> : null}
      </span>
      {trailing != null ? <span className="list-row-action">{trailing}</span> : null}
      {action != null ? <span className="list-row-action">{action}</span> : null}
      {onClick || href ? <ChevronRight size={16} className="text-3" aria-hidden="true" /> : null}
    </>
  );
  if (href) {
    return <Link to={href} className={classes}>{content}</Link>;
  }
  if (onClick) {
    return <button type="button" className={classes} onClick={onClick} disabled={disabled}>{content}</button>;
  }
  return <div className={classes}>{content}</div>;
}

/** Hairline separator between logical list blocks. */
export function ListSep() {
  return <div className="list-sep" role="separator" />;
}

export { Fragment };
