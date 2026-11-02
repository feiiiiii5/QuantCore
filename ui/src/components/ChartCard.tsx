import type { ReactNode } from "react";
import clsx from "clsx";
import EmptyState from "./EmptyState";
import Skeleton from "./Skeleton";

export interface ChartCardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  height?: number;
  loading?: boolean;
  error?: ReactNode;
  onRetry?: () => void;
  empty?: ReactNode;
  children?: ReactNode;
  className?: string;
}

/** Chart container with loading/empty/error states. */
export default function ChartCard({ title, subtitle, actions, height = 320, loading, error, onRetry, empty, children, className }: ChartCardProps) {
  const hasContent = children != null && children !== false;
  return (
    <section className={clsx("chart-card", className)}>
      {title != null || actions != null ? (
        <header className="card-head">
          <div style={{ minWidth: 0 }}>
            {title != null ? <div className="card-title">{title}</div> : null}
            {subtitle != null ? <div className="card-sub">{subtitle}</div> : null}
          </div>
          {actions != null ? <div className="card-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="chart-body" style={{ minHeight: height }}>
        {loading ? <Skeleton variant="tile" rows={1} height={Math.min(height, 220)} /> : null}
        {!loading && error != null ? (
          <div className="chart-empty">
            <EmptyState compact title="图表加载失败" hint={String(error)} action={onRetry ? <button className="btn btn-secondary btn-sm" onClick={onRetry}>重试</button> : undefined} />
          </div>
        ) : null}
        {!loading && error == null && !hasContent ? (
          <div className="chart-empty">{empty ?? <EmptyState compact title="暂无图表数据" hint="选择数据后显示。" />}</div>
        ) : null}
        {!loading && error == null && hasContent ? children : null}
      </div>
    </section>
  );
}
