import { NavLink, Route, Routes } from "react-router-dom";
import {
  BarChart3,
  Database,
  FlaskConical,
  LineChart,
  ListFilter,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import { zhCN as t } from "./i18n/zh-CN";
import StatusBar from "./components/StatusBar";
import MarketPage from "./pages/MarketPage";
import ScreenerPage from "./pages/ScreenerPage";
import StrategyPage from "./pages/StrategyPage";
import BacktestPage from "./pages/BacktestPage";
import ExperimentPage from "./pages/ExperimentPage";
import DataPage from "./pages/DataPage";
import SettingsPage from "./pages/SettingsPage";

const nav = [
  { to: "/", label: t.nav.market, icon: LineChart, end: true },
  { to: "/screener", label: t.nav.screener, icon: ListFilter },
  { to: "/strategy", label: t.nav.strategy, icon: SlidersHorizontal },
  { to: "/backtest", label: t.nav.backtest, icon: BarChart3 },
  { to: "/experiments", label: t.nav.experiments, icon: FlaskConical },
  { to: "/data", label: t.nav.data, icon: Database },
  { to: "/settings", label: t.nav.settings, icon: Settings },
];

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">QC</span>
          <div>
            <strong>{t.appName}</strong>
            <small>{t.tagline}</small>
          </div>
        </div>
        <nav>
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">{t.disclaimer}</div>
      </aside>
      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="搜索代码 / 名称 / 拼音首字母（⌘K）" />
          <div className="topbar-meta">A股 · 日线 · 合成/本地数据</div>
        </header>
        <section className="content">
          <Routes>
            <Route path="/" element={<MarketPage />} />
            <Route path="/screener" element={<ScreenerPage />} />
            <Route path="/strategy" element={<StrategyPage />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/experiments" element={<ExperimentPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </section>
        <StatusBar />
      </main>
    </div>
  );
}
