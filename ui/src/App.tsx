import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, Database, FlaskConical, LineChart, ListFilter, Microscope, Moon, Settings,
  SlidersHorizontal, Sparkles, Sun, Wallet,
} from "lucide-react";
import { zhCN as t } from "./i18n/zh-CN";
import GlobalSearch from "./components/GlobalSearch";
import Toasts from "./components/Toasts";
import StatusBar from "./components/StatusBar";
import Onboarding from "./components/Onboarding";
import ErrorBoundary from "./components/ErrorBoundary";
import MarketPage from "./pages/MarketPage";
import ScreenerPage from "./pages/ScreenerPage";
import BacktestPage from "./pages/BacktestPage";
import ExperimentPage from "./pages/ExperimentPage";
import ResearchPage from "./pages/ResearchPage";
import PaperPage from "./pages/PaperPage";
import DataPage from "./pages/DataPage";
import SettingsPage from "./pages/SettingsPage";
import { useWorkspace } from "./store/workspace";

const StrategyPage = lazy(() => import("./pages/StrategyPage"));

const nav = [
  { to: "/", label: t.nav.market, icon: LineChart, end: true },
  { to: "/screener", label: t.nav.screener, icon: ListFilter },
  { to: "/strategy", label: t.nav.strategy, icon: SlidersHorizontal },
  { to: "/backtest", label: t.nav.backtest, icon: BarChart3 },
  { to: "/experiments", label: t.nav.experiments, icon: FlaskConical },
  { to: "/research", label: t.nav.research, icon: Microscope },
  { to: "/paper", label: t.nav.paper, icon: Wallet },
  { to: "/data", label: t.nav.data, icon: Database },
  { to: "/settings", label: t.nav.settings, icon: Settings },
];

function applyTheme(): void {
  const root = document.documentElement;
  root.dataset.theme = localStorage.getItem("qc_theme") || "light";
  root.dataset.density = localStorage.getItem("qc_density") || "comfortable";
  root.dataset.colorMode = localStorage.getItem("qc_color_mode") || "red-up";
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("qc_theme") || "light");
  const [onboarding, setOnboarding] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const restored = useRef(false);
  const initialLastPath = useRef(useWorkspace.getState().lastPath).current;
  const navigate = useNavigate();
  const location = useLocation();
  const setLastPath = useWorkspace((state) => state.setLastPath);

  useEffect(() => {
    applyTheme();
    const onSettings = () => { applyTheme(); setTheme(localStorage.getItem("qc_theme") || "light"); };
    window.addEventListener("qc-settings", onSettings);
    return () => window.removeEventListener("qc-settings", onSettings);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    setLastPath(location.pathname);
    const item = nav.find((entry) => entry.to === location.pathname);
    document.title = item ? `${item.label} · QuantCore` : "QuantCore";
  }, [location.pathname, setLastPath]);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const last = initialLastPath;
    if (window.location.pathname === "/" && !window.location.search && last !== "/" && nav.some((entry) => entry.to === last)) {
      navigate(last, { replace: true });
    }
  }, [navigate, initialLastPath]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = Boolean(target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable));
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (!typing && event.key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (!typing && event.altKey && /^[1-8]$/.test(event.key)) {
        event.preventDefault();
        const entry = nav[Number(event.key) - 1];
        if (entry) navigate(entry.to);
        return;
      }
      if (event.key === "Escape" && document.activeElement === searchRef.current) {
        searchRef.current?.blur();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    localStorage.setItem("qc_theme", next);
    setTheme(next);
    document.documentElement.dataset.theme = next;
  };

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">QC</span>
          <div><strong>{t.appName}</strong><small>{t.tagline}</small></div>
        </div>
        <nav>
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")} title={`${label} (Alt+${nav.findIndex((item) => item.to === to) + 1})`}>
              <Icon size={18} aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <button className="btn sidebar-cta" onClick={() => setOnboarding(true)}><Sparkles size={15} /> 一键示例</button>
        <div className="sidebar-foot">{t.disclaimer}</div>
      </aside>
      <main className="main">
        <header className="topbar">
          <GlobalSearch ref={searchRef} />
          <div className="topbar-meta">A股 · 日线 · 本地数据</div>
          <button className="icon-btn" onClick={toggleTheme} aria-label="切换主题">{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
        </header>
        <section className="content">
          <ErrorBoundary>
            <Suspense fallback={<div className="state-panel">加载页面…</div>}>
              <Routes>
                <Route path="/" element={<MarketPage />} />
                <Route path="/screener" element={<ScreenerPage />} />
                <Route path="/strategy" element={<StrategyPage />} />
                <Route path="/backtest" element={<BacktestPage />} />
                <Route path="/experiments" element={<ExperimentPage />} />
                <Route path="/research" element={<ResearchPage />} />
            <Route path="/paper" element={<PaperPage />} />
                <Route path="/data" element={<DataPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </section>
        <StatusBar />
      </main>
      <Toasts />
      {onboarding ? <Onboarding onDone={(runId) => { setOnboarding(false); navigate(`/experiments?run=${encodeURIComponent(runId)}`); }} onClose={() => setOnboarding(false)} /> : null}
    </div>
  );
}
