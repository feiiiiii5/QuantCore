import { useRef, useState, type ReactNode } from "react";
import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";

interface VirtualTableProps<T> {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  rowKey: (row: T) => string;
  height?: number;
  rowHeight?: number;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  initialSorting?: SortingState;
  className?: string;
  ariaLabel?: string;
}

export default function VirtualTable<T>({
  data, columns, rowKey, height = 420, rowHeight = 38, empty, onRowClick, initialSorting = [], className, ariaLabel,
}: VirtualTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const scrollRef = useRef<HTMLDivElement>(null);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;
  const headers = table.getHeaderGroups()[0]?.headers ?? [];
  const widths = headers.map((header) => Math.max(header.column.columnDef.size ?? 140, 90));
  const template = widths.map((width) => `${width}px`).join(" ");
  const totalWidth = widths.reduce((sum, width) => sum + width, 0);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 10,
  });

  return (
    <div className={`vtable ${className ?? ""}`} style={{ height }} role="table" aria-label={ariaLabel} aria-rowcount={rows.length}>
      <div ref={scrollRef} className="vtable-scroll">
        <div className="vtable-inner" style={{ minWidth: totalWidth }}>
          <div className="vtable-head" style={{ gridTemplateColumns: template }} role="row">
            {headers.map((header) => {
              const sorted = header.column.getIsSorted();
              const sortable = header.column.getCanSort();
              return (
                <button
                  key={header.id}
                  type="button"
                  className={`vtable-cell vtable-head-cell ${sortable ? "sortable" : ""}`}
                  onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                  aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                >
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  {sorted === "asc" ? " ↑" : sorted === "desc" ? " ↓" : ""}
                </button>
              );
            })}
          </div>
          {rows.length === 0 ? (
            <div className="vtable-empty">{empty ?? <span className="muted">暂无数据</span>}</div>
          ) : (
            <div className="vtable-body" style={{ height: virtualizer.getTotalSize() }}>
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const row = rows[virtualRow.index];
                return (
                  <div
                    key={`${rowKey(row.original)}-${virtualRow.index}`}
                    role="row"
                    className={`vtable-row ${onRowClick ? "clickable" : ""}`}
                    style={{ gridTemplateColumns: template, height: virtualRow.size, transform: `translateY(${virtualRow.start}px)` }}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    tabIndex={onRowClick ? 0 : -1}
                    onKeyDown={(event) => { if (event.key === "Enter" && onRowClick) onRowClick(row.original); }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <div key={cell.id} className="vtable-cell" role="cell">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      {rows.length > 0 ? <div className="vtable-foot">{rows.length.toLocaleString("zh-CN")} 行 · 键盘可 Tab/Enter 选择</div> : null}
    </div>
  );
}
