import { Link } from "react-router-dom";
import { Moon, Search, Sun } from "lucide-react";
import { useLiveIndices, useLiveStatus } from "../api/queries";
import { indexViews, liveSummary, liveTone, marketPhaseLabel } from "../lib/live";
import { signedPct } from "../lib/format";
import { useBeginner, useUIStore } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";

export interface AppBarProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}

const DOT_CLASS: Record<string, string> = { live: "dot live pulse", closed: "dot closed", offline: "dot offline", error: "dot error" };

/** 56px top bar: brand · live index strip · ⌘K · beginner mode · theme. */
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

  return (
    <header className="appbar">
      <Link className="brand" to="/today" aria-label={`${t.appName} · ${t.nav.today}`}>
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
              <span className={`index-chip-pct ${(view.changePct ?? 0) >= 0 ? "up" : "down"}`}>
                {signedPct(view.changePct == null ? null : view.changePct / 100)}
              </span>
            </Link>
          ))
        ) : liveEnabled ? (
          <span className="index-chip">
            <span className="index-chip-name">{t.appbar.connecting}</span>
            <span className="muted small">{status.data?.notice || "等待首个行情帧"}</span>
          </span>
        ) : (
          <Link className="index-chip" to="/settings" title={t.appbar.settingsHint}>
            <span className="index-chip-name">{t.appbar.liveOff}</span>
            <span className="muted small">{t.appbar.settingsHint}</span>
          </Link>
        )}
        <span className="live-state" title={liveSummary(status.data)}>
          <span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />
          {liveLabel}
        </span>
      </div>

      <div className="appbar-actions">
        <button
          type="button"
          className="cmd-trigger"
          aria-label={t.appbar.menu}
          onClick={() => setCommandOpen(true)}
        >
          <Search size={14} aria-hidden="true" />
          <span className="cmd-trigger-label">{t.appbar.search}</span>
          <span className="spacer" />
          <span className="kbd">{t.appbar.commandHint}</span>
        </button>
        <button
          type="button"
          className="switch"
          aria-pressed={beginner}
          aria-label={t.appbar.beginner}
          title={`${t.appbar.beginner}：${beginner ? t.common.yes : t.common.no}`}
          onClick={toggleBeginner}
        >
          <span className="switch-track" aria-hidden="true" />
          <span className="switch-label">{t.appbar.beginner}</span>
        </button>
        <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label={t.appbar.theme} title={t.appbar.theme}>
          {theme === "dark" ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}
