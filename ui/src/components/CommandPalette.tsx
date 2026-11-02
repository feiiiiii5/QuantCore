import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "../api/client";
import { qk } from "../api/queries";
import { signedPct } from "../lib/format";

export interface CommandPaletteItem {
  id: string;
  label: string;
  hint?: string;
  group?: string;
  icon?: LucideIcon;
  keywords?: string;
  run: () => void;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  items?: CommandPaletteItem[];
  placeholder?: string;
}

/**
 * ⌘K palette: jump to pages, search securities (snapshot list) and run commands.
 * Securities are fetched only while the palette is open.
 */
export default function CommandPalette({ open, onClose, items = [], placeholder = "搜索证券、页面或命令…" }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const securities = useQuery({
    queryKey: qk.securities("palette:1000"),
    queryFn: () => api.securities("", 1000),
    enabled: open,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const timer = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(timer);
  }, [open]);

  const needle = query.trim().toLowerCase();
  const securityItems = useMemo<CommandPaletteItem[]>(() => {
    if (!needle) return [];
    const rows = securities.data ?? [];
    return rows
      .filter((row) => `${row.code}${row.name}${row.industry}${row.board}`.toLowerCase().includes(needle))
      .slice(0, 6)
      .map((row) => ({
        id: `sec-${row.sec_id}`,
        label: `${row.code}  ${row.name}`,
        hint: signedPct(row.change_pct / 100),
        group: "证券",
        keywords: row.industry,
        run: () => { onClose(); navigate(`/market?code=${encodeURIComponent(row.code)}`); },
      }));
  }, [needle, securities.data, navigate, onClose]);

  const filtered = useMemo(() => {
    const base = needle
      ? items.filter((item) => `${item.label}${item.keywords ?? ""}${item.group ?? ""}`.toLowerCase().includes(needle))
      : items;
    return [...base, ...securityItems];
  }, [items, needle, securityItems]);

  useEffect(() => { setCursor(0); }, [query]);
  useEffect(() => {
    if (cursor > filtered.length - 1) setCursor(Math.max(filtered.length - 1, 0));
  }, [cursor, filtered.length]);

  if (!open) return null;

  const runAt = (index: number) => {
    const item = filtered[index];
    if (!item) return;
    item.run();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
    if (event.key === "ArrowDown") { event.preventDefault(); setCursor((index) => Math.min(index + 1, Math.max(filtered.length - 1, 0))); return; }
    if (event.key === "ArrowUp") { event.preventDefault(); setCursor((index) => Math.max(index - 1, 0)); return; }
    if (event.key === "Enter") { event.preventDefault(); runAt(cursor); }
  };

  let lastGroup = "";
  return (
    <div className="palette-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="命令面板">
        <div className="palette-input">
          <Search size={16} className="muted" aria-hidden="true" />
          <input
            ref={inputRef}
            role="combobox"
            aria-label="命令面板"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-autocomplete="list"
            value={query}
            placeholder={placeholder}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
          />
          <span className="kbd">Esc</span>
        </div>
        <div className="palette-list" id="command-palette-list" role="listbox" aria-label="命令结果">
          {filtered.length === 0 ? <div className="palette-empty">没有匹配结果。试试代码、页面名或「主题」。</div> : null}
          {filtered.map((item, index) => {
            const Icon = item.icon;
            const showGroup = item.group && item.group !== lastGroup;
            lastGroup = item.group ?? lastGroup;
            return (
              <div key={item.id}>
                {showGroup ? <div className="palette-group-label">{item.group}</div> : null}
                <button
                  type="button"
                  role="option"
                  aria-selected={index === cursor}
                  className={index === cursor ? "palette-item active" : "palette-item"}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => runAt(index)}
                >
                  {Icon ? <Icon size={15} aria-hidden="true" /> : null}
                  <span className="label">{item.label}</span>
                  {item.hint ? <span className="hint">{item.hint}</span> : null}
                </button>
              </div>
            );
          })}
        </div>
        <div className="palette-foot">
          <span>↑↓ 选择</span><span>Enter 打开</span><span>Esc 关闭</span>
          <span className="spacer" />
          <span>⌘K / Ctrl-K</span>
        </div>
      </div>
    </div>
  );
}
