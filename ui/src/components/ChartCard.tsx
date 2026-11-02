import type { ReactNode } from "react";
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
    <section className={className ? `chart-card ${className}` : "chart-card"}>
      {title || actions ? (
        <header className="chart-card-head">
          <div>
            {title ? <h3 className="panel-title">{title}</h3> : null}
            {subtitle ? <div className="panel-subtitle">{subtitle}</div> : null}
          </div>
          {actions ? <div className="panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="chart-card-body" style={{ minHeight: height }}>
        {loading ? <Skeleton variant="tile" rows={1} height={Math.min(height, 220)} /> : null}
        {!loading && error ? (
          <EmptyState compact icon={undefined} title="图表加载失败" hint={String(error)} action={onRetry ? <button className="btn sm" onClick={onRetry}>重试</button> : undefined} />
        ) : null}
        {!loading && !error && !hasContent ? (empty ?? <EmptyState compact title="暂无图表数据" hint="选择数据后显示。" />) : null}
        {!loading && !error && hasContent ? children : null}
      </div>
    </section>
  );
}
