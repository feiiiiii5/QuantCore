import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
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

const EASE = [0.32, 0.72, 0, 1] as const;

/**
 * ⌘K command palette built on cmdk (fuzzy filter + keyboard nav) with framer-motion depth.
 * Securities are fetched only while the palette is open.
 */
export default function CommandPalette({ open, onClose, items = [], placeholder = "搜索证券、页面或命令…" }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const securities = useQuery({
    queryKey: qk.securities("palette:1000"),
    queryFn: () => api.securities("", 1000),
    enabled: open,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const groups = useMemo(() => {
    const ordered: { name: string; items: CommandPaletteItem[] }[] = [];
    for (const item of items) {
      const name = item.group ?? "命令";
      const bucket = ordered.find((group) => group.name === name);
      if (bucket) bucket.items.push(item);
      else ordered.push({ name, items: [item] });
    }
    return ordered;
  }, [items]);

  const securityItems = useMemo<CommandPaletteItem[]>(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [];
    return (securities.data ?? [])
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
  }, [query, securities.data, navigate, onClose]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="cmdk-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: EASE }}
          onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
        >
          <motion.div
            className="cmdk-root"
            role="dialog"
            aria-modal="true"
            aria-label="命令面板"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 4 }}
            transition={{ duration: 0.18, ease: EASE }}
          >
            <Command label="命令面板" loop>
              <div className="cmdk-input-wrap">
                <Search size={16} className="text-3" aria-hidden="true" />
                <Command.Input
                  className="cmdk-input"
                  autoFocus
                  value={query}
                  onValueChange={setQuery}
                  placeholder={placeholder}
                  aria-label="命令面板"
                />
                <span className="kbd">Esc</span>
              </div>
              <Command.List className="cmdk-list">
                <Command.Empty className="cmdk-empty">没有匹配结果。试试代码、页面名或「主题」。</Command.Empty>
                {groups.map((group) => (
                  <Command.Group key={group.name} heading={group.name} className="cmdk-group">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <Command.Item
                          key={item.id}
                          value={`${item.label} ${item.keywords ?? ""} ${item.group ?? ""}`}
                          className="cmdk-item"
                          onSelect={() => { onClose(); item.run(); }}
                        >
                          {Icon ? <span className="cmdk-item-icon"><Icon size={15} aria-hidden="true" /></span> : null}
                          <span className="cmdk-item-label">{item.label}</span>
                          {item.hint ? <span className="cmdk-item-hint">{item.hint}</span> : null}
                        </Command.Item>
                      );
                    })}
                  </Command.Group>
                ))}
                {securityItems.length ? (
                  <Command.Group heading="证券" className="cmdk-group">
                    {securityItems.map((item) => (
                      <Command.Item
                        key={item.id}
                        value={`${item.label} ${item.keywords ?? ""} 证券`}
                        className="cmdk-item"
                        onSelect={() => { onClose(); item.run(); }}
                      >
                        <span className="cmdk-item-label">{item.label}</span>
                        {item.hint ? <span className="cmdk-item-hint">{item.hint}</span> : null}
                      </Command.Item>
                    ))}
                  </Command.Group>
                ) : null}
              </Command.List>
              <div className="cmdk-footer">
                <span>↑↓ 选择</span><span>Enter 打开</span><span>Esc 关闭</span>
                <span className="spacer" />
                <span>⌘K / Ctrl-K</span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
