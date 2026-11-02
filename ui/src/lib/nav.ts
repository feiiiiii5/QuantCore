import {
  BarChart3, Database, FlaskConical, Home, LineChart, ListFilter, Microscope, Settings,
  SlidersHorizontal, Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { zhCN as t } from "../i18n/zh-CN";

export type NavGroupKey = "today" | "market" | "research" | "paper" | "data" | "settings";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  group: NavGroupKey;
  /** Alt+digit / g+digit shortcut (1–9, 0 = 10th). */
  shortcut: number;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/today", label: t.nav.today, icon: Home, group: "today", shortcut: 1 },
  { to: "/market", label: t.nav.market, icon: LineChart, group: "market", shortcut: 2 },
  { to: "/screener", label: t.nav.screener, icon: ListFilter, group: "research", shortcut: 3 },
  { to: "/strategy", label: t.nav.strategy, icon: SlidersHorizontal, group: "research", shortcut: 4 },
  { to: "/backtest", label: t.nav.backtest, icon: BarChart3, group: "research", shortcut: 5 },
  { to: "/experiments", label: t.nav.experiments, icon: FlaskConical, group: "research", shortcut: 6 },
  { to: "/research", label: t.nav.research, icon: Microscope, group: "research", shortcut: 7 },
  { to: "/paper", label: t.nav.paper, icon: Wallet, group: "paper", shortcut: 8 },
  { to: "/data", label: t.nav.data, icon: Database, group: "data", shortcut: 9 },
  { to: "/settings", label: t.nav.settings, icon: Settings, group: "settings", shortcut: 0 },
];

const GROUP_ORDER: NavGroupKey[] = ["today", "market", "research", "paper", "data", "settings"];

export interface NavGroup {
  key: NavGroupKey;
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = GROUP_ORDER.map((key) => ({
  key,
  label: t.nav.groups[key],
  items: NAV_ITEMS.filter((item) => item.group === key),
}));

export function navItemByShortcut(digit: number): NavItem | undefined {
  return NAV_ITEMS.find((item) => item.shortcut === digit);
}

/** Page title for document.title / palette; undefined when the path is unknown. */
export function titleForPath(pathname: string): string | undefined {
  const hit = NAV_ITEMS.find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`));
  return hit?.label;
}

/** Routes that belong to one mobile tab group. */
export function groupRoutes(group: NavGroupKey): string[] {
  return NAV_ITEMS.filter((item) => item.group === group).map((item) => item.to);
}
