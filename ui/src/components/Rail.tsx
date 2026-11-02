import { NavLink, useLocation } from "react-router-dom";
import { NAV_GROUPS, groupRoutes, type NavGroupKey } from "../lib/nav";

/** Icon rail (68px) with grouped navigation; Alt+digit shortcuts are wired in App. */
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
              title={`${label}（Alt+${shortcut === 0 ? 0 : shortcut}）`}
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

const MOBILE_GROUPS: { key: NavGroupKey; to: string; label: string }[] = [
  { key: "today", to: "/today", label: "今日" },
  { key: "market", to: "/market", label: "行情" },
  { key: "research", to: "/backtest", label: "研究" },
  { key: "paper", to: "/paper", label: "模拟" },
  { key: "data", to: "/data", label: "数据" },
  { key: "settings", to: "/settings", label: "设置" },
];

/** Bottom tab bar shown below 900px; mirrors the rail groups. */
export function MobileTabBar() {
  const location = useLocation();
  return (
    <nav className="mobile-tabbar" aria-label="底部导航">
      {MOBILE_GROUPS.map((group) => {
        const active = groupRoutes(group.key).some((route) => location.pathname === route || location.pathname.startsWith(`${route}/`));
        return (
          <NavLink key={group.key} to={group.to} className={active ? "active" : ""}>
            <span>{group.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
