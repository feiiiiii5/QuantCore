import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Moon, Search, Sun } from "lucide-react";
import { useLiveIndices, useLiveStatus } from "../api/queries";
import { indexViews, liveSummary, liveTone, marketPhaseLabel } from "../lib/live";
import { signedPct } from "../lib/format";
import { useBeginner, useUIStore } from "../store/ui";
import Switch from "./Switch";
import Tooltip from "./Tooltip";
import { zhCN as t } from "../i18n/zh-CN";

export interface AppBarProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}

const DOT_CLASS: Record<string, string> = { live: "dot live pulse", closed: "dot closed", offline: "dot offline", error: "dot error" };

/** 52px glass app bar: brand · live index strip · ⌘K · beginner switch · theme. */
export default function AppBar({ theme, onToggleTheme }: AppBarProps) {
  const beginner = useBeginner();
  const toggleBeginner = useUIStore((state) => state.toggleBeginner);
  const setCommandOpen = useUIStore((state) => state.setCommandOpen);
  const status = useLiveStatus();
  const liveEnabled = Boolean(status.data?.enabled);
  const indices = useLiveIndices(liveEnabled);
  const views = indexViews(indices.data?.quotes, null);
  const tone = liveTone(status.data);
  const phase = status.data?.enabled ? marketPhaseLabel(status.data.market.phase) : t.appbar.offline;
  const liveLabel = status.data?.enabled ? phase : t.appbar.offline;
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const content = document.querySelector(".app-content");
    if (!(content instanceof HTMLElement)) return;
    const onScroll = () => setScrolled(content.scrollTop > 8);
    content.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => content.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className="appbar" data-scrolled={scrolled}>
      <Link className="appbar-brand" to="/today" aria-label={`${t.appName} · ${t.nav.today}`}>
        <span className="brand-mark" aria-hidden="true">QC</span>
        <span>
          <span className="brand-name">{t.appName}</span>
          <span className="brand-tagline">{t.tagline}</span>
        </span>
      </Link>

      <div className="appbar-indices" aria-label="指数实时条">
        {liveEnabled && views.some((view) => view.close != null) ? (
          views.map((view) => (
            <Link key={view.key} className="index-chip" to="/market" title={`${view.name} · ${view.source === "live" ? t.appbar.live : t.common.snapshot}`}>
              <span className="index-chip-name">{view.name}</span>
              <span className="index-chip-value">{view.close?.toFixed(2) ?? "—"}</span>
              <span className={`index-chip-pct ${(view.changePct ?? 0) >= 0 ? "delta-up" : "delta-down"}`}>
                {signedPct(view.changePct == null ? null : view.changePct / 100)}
              </span>
            </Link>
          ))
        ) : liveEnabled ? (
          <span className="index-chip">
            <span className="index-chip-name">{t.appbar.connecting}</span>
            <span className="caption2 text-3">{status.data?.notice || "等待首个行情帧"}</span>
          </span>
        ) : (
          <Link className="index-chip" to="/settings" title={t.appbar.settingsHint}>
            <span className="index-chip-name">{t.appbar.liveOff}</span>
            <span className="caption2 text-3">{t.appbar.settingsHint}</span>
          </Link>
        )}
        <span className="appbar-divider" aria-hidden="true" />
        <span className="live-state" title={liveSummary(status.data)}>
          <span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />
          {liveLabel}
        </span>
      </div>

      <div className="appbar-actions">
        <button type="button" className="cmd-trigger" aria-label={t.appbar.menu} onClick={() => setCommandOpen(true)}>
          <Search size={14} aria-hidden="true" />
          <span className="cmd-trigger-label">{t.appbar.search}</span>
          <span className="spacer" />
          <span className="kbd">{t.appbar.commandHint}</span>
        </button>
        <Switch checked={beginner} onChange={toggleBeginner} ariaLabel={t.appbar.beginner} />
        <Tooltip content={t.appbar.theme}>
          <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label={t.appbar.theme}>
            {theme === "dark" ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
          </button>
        </Tooltip>
      </div>
    </header>
  );
}
