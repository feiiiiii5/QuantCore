import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { BarChart3, Database, FlaskConical, Home, LineChart, ListFilter, Microscope, Settings, SlidersHorizontal, User, Wallet } from "lucide-react";
import { NAV_GROUPS, groupRoutes, type NavGroupKey } from "../lib/nav";
import Sheet from "./Sheet";
import List, { ListRow } from "./List";
import { zhCN as t } from "../i18n/zh-CN";

/** 64px glass icon rail with grouped navigation; Alt+digit shortcuts are wired in App. */
export default function Rail() {
  return (
    <aside className="rail" aria-label="主导航">
      {NAV_GROUPS.map((group) => (
        <div className="rail-group" key={group.key}>
          {group.items.length > 1 ? <div className="rail-group-label">{group.label}</div> : null}
          {group.items.map(({ to, label, icon: Icon, shortcut }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/today"}
              className={({ isActive }) => (isActive ? "rail-item active" : "rail-item")}
              title={`${label}（Alt+${shortcut}）`}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      ))}
      <div className="rail-foot">
        <small>仅研究<br />不构成投资建议</small>
      </div>
    </aside>
  );
}

const TABS: { to: string; label: string; icon: typeof Home; groups: NavGroupKey[] }[] = [
  { to: "/today", label: "今日", icon: Home, groups: ["today"] },
  { to: "/market", label: "行情", icon: LineChart, groups: ["market"] },
  { to: "/backtest", label: "回测", icon: BarChart3, groups: ["research"] },
  { to: "/data", label: "数据", icon: Database, groups: ["data"] },
];

const MORE: { to: string; label: string; icon: typeof Home }[] = [
  { to: "/screener", label: t.nav.screener, icon: ListFilter },
  { to: "/strategy", label: t.nav.strategy, icon: SlidersHorizontal },
  { to: "/experiments", label: t.nav.experiments, icon: FlaskConical },
  { to: "/research", label: t.nav.research, icon: Microscope },
  { to: "/paper", label: t.nav.paper, icon: Wallet },
  { to: "/settings", label: t.nav.settings, icon: Settings },
];

/** matchMedia breakpoint guard: the tab bar only mounts on small screens (keeps desktop DOM clean). */
function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => (
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(max-width: 1023px)").matches
      : false
  ));
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 1023px)");
    const onChange = () => setMobile(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return mobile;
}

/** iOS-style bottom tab bar (<1024px) with a vaul sheet for secondary navigation. */
export function MobileTabBar() {
  const mobile = useIsMobile();
  const location = useLocation();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);
  const isActive = (groups: NavGroupKey[]) => groups.some((group) =>
    groupRoutes(group).some((route) => location.pathname === route || location.pathname.startsWith(`${route}/`)));
  if (!mobile) return null;
  return (
    <>
      <nav className="mobile-tabbar" aria-label="底部导航">
        {TABS.map(({ to, label, icon: Icon, groups }) => (
          <NavLink key={to} to={to} className={() => (isActive(groups) ? "active" : "")}>
            <Icon size={20} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
        <button type="button" onClick={() => setMoreOpen(true)} className={isActive(["paper", "settings", "research"]) && !isActive(["research"]) ? "active" : ""}>
          <User size={20} aria-hidden="true" />
          <span>我的</span>
        </button>
      </nav>
      <Sheet open={moreOpen} onOpenChange={setMoreOpen} side="bottom" title="更多">
        <List>
          {MORE.map(({ to, label, icon: Icon }) => (
            <ListRow
              key={to}
              title={label}
              leading={<Icon size={17} aria-hidden="true" />}
              onClick={() => { setMoreOpen(false); navigate(to); }}
            />
          ))}
        </List>
        <p className="caption2 text-3" style={{ marginTop: "var(--sp-5)" }}>仅研究与模拟，不构成投资建议。</p>
      </Sheet>
    </>
  );
}
