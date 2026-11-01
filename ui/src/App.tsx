import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { BarChart3, Database, FlaskConical, LineChart, ListFilter, Microscope, Moon, Settings, SlidersHorizontal, Sparkles, Sun } from "lucide-react";
import { zhCN as t } from "./i18n/zh-CN";
import { api } from "./api/client";
import type { SecurityRow } from "./api/types";
import StatusBar from "./components/StatusBar";
import Onboarding from "./components/Onboarding";
import MarketPage from "./pages/MarketPage";
import ScreenerPage from "./pages/ScreenerPage";
const StrategyPage = lazy(() => import("./pages/StrategyPage"));
import BacktestPage from "./pages/BacktestPage";
import ExperimentPage from "./pages/ExperimentPage";
import ResearchPage from "./pages/ResearchPage";
import DataPage from "./pages/DataPage";
import SettingsPage from "./pages/SettingsPage";

const nav = [
  { to: "/", label: t.nav.market, icon: LineChart, end: true },
  { to: "/screener", label: t.nav.screener, icon: ListFilter },
  { to: "/strategy", label: t.nav.strategy, icon: SlidersHorizontal },
  { to: "/backtest", label: t.nav.backtest, icon: BarChart3 },
  { to: "/experiments", label: t.nav.experiments, icon: FlaskConical },
  { to: "/research", label: t.nav.research, icon: Microscope },
  { to: "/data", label: t.nav.data, icon: Database },
  { to: "/settings", label: t.nav.settings, icon: Settings },
];

export default function App() {
  const [theme, setTheme] = useState(localStorage.getItem("qc_theme") || "light");
  const [density, setDensity] = useState(localStorage.getItem("qc_density") || "comfortable");
  const [colorMode, setColorMode] = useState(localStorage.getItem("qc_color_mode") || "red-up");
  const [onboarding, setOnboarding] = useState(false);
  const [search, setSearch] = useState("");
  const [hits, setHits] = useState<SecurityRow[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const apply = () => {
    document.documentElement.dataset.theme = localStorage.getItem("qc_theme") || "light";
    document.documentElement.dataset.density = localStorage.getItem("qc_density") || "comfortable";
    document.documentElement.dataset.colorMode = localStorage.getItem("qc_color_mode") || "red-up";
    setTheme(localStorage.getItem("qc_theme") || "light");
    setDensity(localStorage.getItem("qc_density") || "comfortable");
    setColorMode(localStorage.getItem("qc_color_mode") || "red-up");
  };
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.density = density;
    document.documentElement.dataset.colorMode = colorMode;
  }, [theme, density, colorMode]);
  useEffect(() => {
    const handler = () => apply();
    window.addEventListener("qc-settings", handler);
    return () => window.removeEventListener("qc-settings", handler);
  }, []);

  useEffect(() => {
    if (!search.trim()) { setHits([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api.securities(search.trim(), 8)
        .then((rows) => { if (!cancelled) setHits(rows); })
        .catch(() => { if (!cancelled) setHits([]); });
    }, 180);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [search]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape") { setHits([]); searchRef.current?.blur(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openHit = (hit: SecurityRow) => {
    setSearch(""); setHits([]);
    navigate(`/?code=${encodeURIComponent(hit.code)}`);
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    localStorage.setItem("qc_theme", next); setTheme(next);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">QC</span>
          <div><strong>{t.appName}</strong><small>{t.tagline}</small></div>
        </div>
        <nav>
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={18} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <button className="btn sidebar-cta" onClick={() => setOnboarding(true)}><Sparkles size={15} /> 一键示例</button>
        <div className="sidebar-foot">{t.disclaimer}</div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="global-search">
            <input
              ref={searchRef}
              className="search"
              placeholder="搜索代码 / 名称 / 行业（⌘K）"
              aria-label="全局搜索"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter" && hits[0]) openHit(hits[0]); }}
            />
            {hits.length > 0 ? (
              <div className="search-menu" role="listbox" aria-label="搜索建议">
                {hits.map((hit) => (
                  <button key={hit.sec_id} type="button" className="search-hit" onClick={() => openHit(hit)}>
                    <span className="mono">{hit.code}</span>
                    <span>{hit.name}</span>
                    <small>{hit.industry}</small>
                    <span className={hit.change_pct >= 0 ? "up" : "down"}>{hit.change_pct >= 0 ? "+" : ""}{hit.change_pct.toFixed(2)}%</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="topbar-meta">A股 · 日线 · 本地数据</div>
          <button className="icon-btn" onClick={toggleTheme} aria-label="切换主题">{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
        </header>
        <section className="content">
          <Routes>
            <Route path="/" element={<MarketPage />} />
            <Route path="/screener" element={<ScreenerPage />} />
            <Route path="/strategy" element={<Suspense fallback={<div className="state-panel">加载策略编辑器…</div>}><StrategyPage /></Suspense>} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/experiments" element={<ExperimentPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </section>
        <StatusBar />
      </main>
      {onboarding ? <Onboarding onDone={(runId) => { setOnboarding(false); navigate(`/experiments?run=${encodeURIComponent(runId)}`); }} onClose={() => setOnboarding(false)} /> : null}
    </div>
  );
}
