import type { ReactNode } from "react";
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
  const classes = ["data-table"];
  if (dense) classes.push("dense");
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")}>
      {loading ? (
        <div style={{ padding: "var(--sp-3)" }}><Skeleton variant="row" rows={Math.min(rows.length || 6, 8)} /></div>
      ) : rows.length === 0 ? (
        <div className="data-table-empty">{empty ?? <EmptyState compact title="暂无数据" hint="调整筛选条件或先运行一次任务。" />}</div>
      ) : (
        <div className="data-table-scroll" style={maxHeight ? { maxHeight } : undefined}>
          <table aria-label={ariaLabel}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    className={[column.align ?? "left", column.className ?? ""].join(" ").trim()}
                    style={column.width ? { width: column.width } : undefined}
                    scope="col"
                  >
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const key = rowKey(row);
                const rowClasses = [onRowClick ? "clickable" : "", selectedKey === key ? "selected" : ""].join(" ").trim();
                return (
                  <tr
                    key={key}
                    className={rowClasses || undefined}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    onKeyDown={onRowClick ? (event) => { if (event.key === "Enter") onRowClick(row); } : undefined}
                  >
                    {columns.map((column) => (
                      <td key={column.key} className={[column.align ?? "left", column.className ?? ""].join(" ").trim()}>
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
      {footer ? <div className="data-table-foot">{footer}</div> : null}
    </div>
  );
}
