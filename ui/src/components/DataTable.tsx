import type { ReactNode } from "react";
import clsx from "clsx";
import Skeleton from "./Skeleton";
import EmptyState from "./EmptyState";

export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  width?: number | string;
  align?: "left" | "right" | "center";
  render?: (row: T, index: number) => ReactNode;
  sortValue?: (row: T) => number | string;
  className?: string;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  dense?: boolean;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  empty?: ReactNode;
  loading?: boolean;
  maxHeight?: number;
  ariaLabel?: string;
  footer?: ReactNode;
  className?: string;
}

/** Lightweight table with loading/empty states; use VirtualTable for 1000+ rows. */
export default function DataTable<T>({
  columns, rows, rowKey, dense, onRowClick, selectedKey, empty, loading, maxHeight, ariaLabel, footer, className,
}: DataTableProps<T>) {
  return (
    <div className="data-table">
      {loading ? (
        <div style={{ padding: "var(--sp-4)" }}><Skeleton variant="row" rows={Math.min(rows.length || 6, 8)} /></div>
      ) : rows.length === 0 ? (
        <div className="table-empty">{empty ?? <EmptyState compact title="暂无数据" hint="调整筛选条件或先运行一次任务。" />}</div>
      ) : (
        <div
          className={clsx("table-wrap", "table-row-hover", dense && "dense", className)}
          style={maxHeight ? { maxHeight, overflowY: "auto" } : undefined}
        >
          <table aria-label={ariaLabel}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    className={clsx(column.align === "right" && "num", column.align === "center" && "center", column.className)}
                    style={column.width ? { width: column.width } : undefined}
                    scope="col"
                    align={column.align === "center" ? "center" : undefined}
                  >
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const key = rowKey(row);
                const selected = selectedKey === key;
                return (
                  <tr
                    key={key}
                    className={clsx(selected && "selected", onRowClick && "row-hover")}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    onKeyDown={onRowClick ? (event) => { if (event.key === "Enter") onRowClick(row); } : undefined}
                  >
                    {columns.map((column) => (
                      <td key={column.key} className={clsx(column.align === "right" && "num", column.align === "center" && "center", column.className)}>
                        {column.render ? column.render(row, index) : String((row as Record<string, unknown>)[column.key] ?? "—")}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {footer ? <div className="caption2 text-3" style={{ padding: "var(--sp-2) 0" }}>{footer}</div> : null}
    </div>
  );
}
