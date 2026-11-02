import type { ReactNode } from "react";
import clsx from "clsx";

export interface PageHeaderBreadcrumb {
  label: ReactNode;
  to?: string;
}

export interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  breadcrumb?: PageHeaderBreadcrumb[];
  className?: string;
}

/** Page title block: 34px title + one-line description + actions on the same baseline. */
export default function PageHeader({ title, subtitle, actions, breadcrumb, className }: PageHeaderProps) {
  return (
    <header className={clsx("page-header", className)}>
      <div className="page-header-main">
        {breadcrumb && breadcrumb.length > 0 ? (
          <nav className="breadcrumb" aria-label="面包屑">
            {breadcrumb.map((item, index) => (
              <span key={index} className="row row-tight">
                {index > 0 ? <span className="breadcrumb-sep">/</span> : null}
                {item.to ? <a href={item.to}>{item.label}</a> : <span>{item.label}</span>}
              </span>
            ))}
          </nav>
        ) : null}
        <h1 className="page-title">{title}</h1>
        {subtitle != null ? <p className="page-sub">{subtitle}</p> : null}
      </div>
      {actions != null ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}
