import { forwardRef, useMemo, useState, type KeyboardEvent } from "react";
import { Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useSecurities } from "../api/queries";
import type { SecurityRow } from "../api/types";
import { signedPct } from "../lib/format";

const GlobalSearch = forwardRef<HTMLInputElement>(function GlobalSearch(_props, ref) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [open, setOpen] = useState(false);
  const { data: securities = [], isFetching, error } = useSecurities("", 1000);
  const navigate = useNavigate();
  const hits = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return [] as SecurityRow[];
    return securities.filter((row) => `${row.code}${row.name}${row.industry}${row.board}`.toLowerCase().includes(needle)).slice(0, 8);
  }, [query, securities]);

  const choose = (row: SecurityRow) => {
    setQuery(""); setOpen(false); setCursor(0);
    navigate(`/?code=${encodeURIComponent(row.code)}`);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") { setOpen(false); event.currentTarget.blur(); return; }
    if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setCursor((index) => Math.min(index + 1, Math.max(hits.length - 1, 0))); return; }
    if (event.key === "ArrowUp") { event.preventDefault(); setCursor((index) => Math.max(index - 1, 0)); return; }
    if (event.key === "Enter" && hits[cursor]) { event.preventDefault(); choose(hits[cursor]); }
  };

  return (
    <div className="global-search">
      <Search size={16} className="search-icon" aria-hidden="true" />
      <input
        ref={ref}
        className="search"
        placeholder="搜索代码 / 名称 / 行业（⌘K）"
        aria-label="全局搜索"
        aria-expanded={open && Boolean(query)}
        aria-controls="global-search-results"
        role="combobox"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(event) => { setQuery(event.target.value); setOpen(true); setCursor(0); }}
        onKeyDown={onKeyDown}
      />
      {open && query.trim() ? (
        <div className="search-menu" id="global-search-results" role="listbox" aria-label="搜索建议">
          {hits.map((hit, index) => (
            <button
              key={hit.sec_id}
              type="button"
              role="option"
              aria-selected={index === cursor}
              className={`search-hit ${index === cursor ? "active" : ""}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(hit)}
              onMouseEnter={() => setCursor(index)}
            >
              <span className="mono">{hit.code}</span>
              <span className="search-hit-name">{hit.name}</span>
              <small>{hit.industry}</small>
              <span className={hit.change_pct >= 0 ? "up" : "down"}>{signedPct(hit.change_pct / 100)}</span>
            </button>
          ))}
          {!hits.length ? <div className="search-empty">{isFetching ? "加载证券…" : error ? "本地服务未连接" : "无匹配证券"}</div> : null}
        </div>
      ) : null}
    </div>
  );
});

export default GlobalSearch;
