import { Suspense, lazy, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Moon, Sparkles, Sun } from "lucide-react";
import AppBar from "./components/AppBar";
import Rail, { MobileTabBar } from "./components/Rail";
import CommandPalette, { type CommandPaletteItem } from "./components/CommandPalette";
import Onboarding from "./components/Onboarding";
import Toasts from "./components/Toasts";
import StatusBar from "./components/StatusBar";
import ErrorBoundary from "./components/ErrorBoundary";
import HomePage from "./pages/HomePage";
import { NAV_ITEMS, navItemByShortcut, titleForPath } from "./lib/nav";
import {
  applyAppearance, readAppearance, subscribeAppearance, toggleTheme, type Appearance,
} from "./lib/appearance";
import { useBeginner, useUIStore } from "./store/ui";
import { useWorkspace } from "./store/workspace";
import { zhCN as t } from "./i18n/zh-CN";

const StrategyPage = lazy(() => import("./pages/StrategyPage"));
const MarketPage = lazy(() => import("./pages/MarketPage"));
const ScreenerPage = lazy(() => import("./pages/ScreenerPage"));
const BacktestPage = lazy(() => import("./pages/BacktestPage"));
const ExperimentPage = lazy(() => import("./pages/ExperimentPage"));
const ResearchPage = lazy(() => import("./pages/ResearchPage"));
const PaperPage = lazy(() => import("./pages/PaperPage"));
const DataPage = lazy(() => import("./pages/DataPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function isTyping(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element) return false;
  return element.tagName === "INPUT" || element.tagName === "TEXTAREA" || element.isContentEditable;
}

export default function App() {
  const [appearance, setAppearanceState] = useState<Appearance>(() => readAppearance());
  const commandOpen = useUIStore((state) => state.commandOpen);
  const setCommandOpen = useUIStore((state) => state.setCommandOpen);
  const onboardingOpen = useUIStore((state) => state.onboardingOpen);
  const openOnboarding = useUIStore((state) => state.openOnboarding);
  const closeOnboarding = useUIStore((state) => state.closeOnboarding);
  const beginner = useBeginner();
  const toggleBeginner = useUIStore((state) => state.toggleBeginner);
  const navigate = useNavigate();
  const location = useLocation();
  const setLastPath = useWorkspace((state) => state.setLastPath);
  const pendingG = useRef(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const pageTransition = reduceMotion
    ? { duration: 0 }
    : { duration: 0.2, ease: [0.32, 0.72, 0, 1] as const };

  useEffect(() => {
    setAppearanceState(applyAppearance());
    return subscribeAppearance(setAppearanceState);
  }, []);

  useEffect(() => {
    setLastPath(location.pathname);
    const label = titleForPath(location.pathname);
    document.title = label ? `${label} · ${t.appName}` : t.appName;
    if (typeof contentRef.current?.scrollTo === "function") {
      contentRef.current.scrollTo({ top: 0, behavior: "auto" });
    }
  }, [location.pathname, setLastPath]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = isTyping(event.target);
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(!useUIStore.getState().commandOpen);
        return;
      }
      if (event.key === "Escape" && useUIStore.getState().commandOpen) {
        setCommandOpen(false);
        return;
      }
      if (typing) return;
      if (event.key === "/") {
        event.preventDefault();
        setCommandOpen(true);
        return;
      }
      if (event.altKey && /^[0-9]$/.test(event.key)) {
        event.preventDefault();
        const item = navItemByShortcut(Number(event.key));
        if (item) navigate(item.to);
        return;
      }
      if (event.key === "g") { pendingG.current = Date.now(); return; }
      if (pendingG.current && Date.now() - pendingG.current < 1200 && /^[0-9]$/.test(event.key)) {
        const item = navItemByShortcut(Number(event.key));
        pendingG.current = 0;
        if (item) { event.preventDefault(); navigate(item.to); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, setCommandOpen]);

  const paletteItems = useMemo<CommandPaletteItem[]>(() => {
    const navItems: CommandPaletteItem[] = NAV_ITEMS.map((item) => ({
      id: `nav-${item.to}`,
      label: item.label,
      hint: `Alt+${item.shortcut}`,
      group: "页面",
      icon: item.icon,
      run: () => { setCommandOpen(false); navigate(item.to); },
    }));
    const commands: CommandPaletteItem[] = [
      {
        id: "cmd-theme",
        label: appearance.theme === "dark" ? "切换到浅色主题" : "切换到深色主题",
        group: "命令",
        icon: appearance.theme === "dark" ? Sun : Moon,
        keywords: "theme dark light 主题 深色 浅色",
        run: () => { setCommandOpen(false); setAppearanceState(toggleTheme()); },
      },
      {
        id: "cmd-beginner",
        label: beginner ? "关闭新手模式" : "开启新手模式",
        group: "命令",
        keywords: "beginner 新手",
        run: () => { setCommandOpen(false); toggleBeginner(); },
      },
      {
        id: "cmd-onboarding",
        label: "打开新手引导（一键示例）",
        group: "命令",
        icon: Sparkles,
        keywords: "onboarding 引导 示例 bootstrap",
        run: () => { setCommandOpen(false); openOnboarding(); },
      },
      {
        id: "cmd-live",
        label: "开启实时行情（去设置）",
        group: "命令",
        keywords: "live 实时 网络",
        run: () => { setCommandOpen(false); navigate("/settings"); },
      },
      {
        id: "cmd-integrity",
        label: "查看数据体检",
        group: "命令",
        keywords: "data integrity 数据 体检",
        run: () => { setCommandOpen(false); navigate("/data"); },
      },
    ];
    return [...navItems, ...commands];
  }, [appearance.theme, beginner, navigate, openOnboarding, setCommandOpen, toggleBeginner]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <AppBar theme={appearance.theme} onToggleTheme={() => setAppearanceState(toggleTheme())} />
      <Rail />
      <main className="app-main" id="main-content">
        <div className="app-content" ref={contentRef}>
          <div className="content-inner">
            <ErrorBoundary>
              <Suspense fallback={<div className="state-panel" role="status">加载页面…</div>}>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={location.pathname}
                    className="page-transition"
                    initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
                    transition={pageTransition}
                  >
                    <Routes location={location}>
                      <Route path="/" element={<Navigate to="/today" replace />} />
                      <Route path="/today" element={<HomePage />} />
                      <Route path="/market" element={<MarketPage />} />
                      <Route path="/screener" element={<ScreenerPage />} />
                      <Route path="/strategy" element={<StrategyPage />} />
                      <Route path="/backtest" element={<BacktestPage />} />
                      <Route path="/experiments" element={<ExperimentPage />} />
                      <Route path="/research" element={<ResearchPage />} />
                      <Route path="/paper" element={<PaperPage />} />
                      <Route path="/data" element={<DataPage />} />
                      <Route path="/settings" element={<SettingsPage />} />
                      <Route path="*" element={<Navigate to="/today" replace />} />
                    </Routes>
                  </motion.div>
                </AnimatePresence>
              </Suspense>
            </ErrorBoundary>
          </div>
        </div>
        <StatusBar />
      </main>
      <MobileTabBar />
      <CommandPalette open={commandOpen} onClose={() => setCommandOpen(false)} items={paletteItems} />
      {onboardingOpen ? (
        <Onboarding
          onDone={(runId) => { closeOnboarding(); navigate(`/experiments?run=${encodeURIComponent(runId)}`); }}
          onClose={closeOnboarding}
        />
      ) : null}
      <Toasts />
    </div>
  );
}
