import type {
  Bars, DataIntegrity, IndexQuote, LiveQuote, LiveState, LiveStatus, MarketPhase, SecurityProfile,
} from "../api/types";
import { dateInt } from "./format";

/** Presentation helpers for the opt-in live market service; never fetch here. */

export type LiveTone = "live" | "closed" | "offline" | "error";

export const INDEX_DEFS = [
  { key: "sh", code: "000001", name: "上证", aliases: ["上证指数", "上证"] },
  { key: "sz", code: "399001", name: "深成", aliases: ["深证成指", "深成指", "深成"] },
  { key: "cyb", code: "399006", name: "创业板", aliases: ["创业板指", "创业板"] },
  { key: "kc50", code: "000688", name: "科创50", aliases: ["科创50", "科创50指数", "科创"] },
] as const;

export interface IndexView {
  key: string;
  name: string;
  close: number | null;
  changePct: number | null;
  spark: number[];
  source: "live" | "snapshot" | "none";
}

function matchIndex<T extends { name: string; code?: string }>(rows: T[], code: string, aliases: readonly string[]): T | undefined {
  return rows.find((row) => row.code === code)
    ?? rows.find((row) => aliases.some((alias) => row.name.includes(alias)));
}

/**
 * Index strip: live quotes map onto the four canonical indices (上证/深成/创业板/科创50);
 * without live data the local snapshot keeps its own four rows (全市场/主板/创业板/科创板)
 * so the offline cards stay consistent and honestly labelled "快照".
 */
export function indexViews(liveQuotes?: LiveQuote[] | null, snapshot?: IndexQuote[] | null): IndexView[] {
  if (liveQuotes?.length) {
    return INDEX_DEFS.map((def) => {
      const hit = matchIndex(liveQuotes, def.code, def.aliases);
      return {
        key: def.key,
        name: def.name,
        close: hit?.price ?? null,
        changePct: hit?.change_pct ?? null,
        spark: [],
        source: hit ? ("live" as const) : ("none" as const),
      };
    });
  }
  if (snapshot?.length) {
    return snapshot.slice(0, 4).map((row, index) => ({
      key: `snapshot-${index}`,
      name: row.name,
      close: row.close,
      changePct: row.change_pct,
      spark: row.spark ?? [],
      source: "snapshot" as const,
    }));
  }
  return INDEX_DEFS.map((def) => ({ key: def.key, name: def.name, close: null, changePct: null, spark: [], source: "none" as const }));
}

const PHASE_LABELS: Record<MarketPhase, string> = {
  pre_open: "未开盘",
  open: "交易中",
  lunch: "午休",
  closed: "休市",
  holiday: "休市",
};

export function marketPhaseLabel(phase?: MarketPhase | null): string {
  return phase ? PHASE_LABELS[phase] ?? phase : "未知";
}

const LIVE_STATE_LABELS: Record<LiveState, string> = {
  off: "实时未开启",
  idle: "待连接",
  connecting: "连接中",
  live: "实时",
  error: "实时异常",
  closed: "休市",
};

export function liveStateLabel(status?: LiveStatus | null): string {
  if (!status) return "离线";
  if (!status.enabled) return "离线快照";
  return LIVE_STATE_LABELS[status.state] ?? status.state;
}

/** Traffic-light tone used by dots/badges in AppBar, StatusBar and Market page. */
export function liveTone(status?: LiveStatus | null): LiveTone {
  if (!status || !status.enabled) return "offline";
  if (status.state === "error") return "error";
  if (status.state === "live") {
    return status.market.phase === "open" ? "live" : "closed";
  }
  if (status.state === "closed") return "closed";
  if (status.state === "connecting" || status.state === "idle") return "offline";
  return "offline";
}

/** e.g. "实时 · 10:32:05" / "休市 · 最近收盘 2024-12-31" / "实时行情未开启". */
export function liveSummary(status?: LiveStatus | null, snapshotDate?: string | null): string {
  if (!status) return "本地服务离线";
  if (!status.enabled) return "实时行情未开启，去设置开启";
  const label = liveStateLabel(status);
  if (status.state === "live" && status.as_of) return `${label} · ${formatClock(status.as_of)}`;
  if (status.state === "error") return status.error || "实时行情异常";
  const last = status.market.last_trade_date ? dateInt(status.market.last_trade_date) : snapshotDate ?? null;
  return last ? `${label} · 最近收盘 ${last}` : label;
}

/** HH:mm:ss in local time; invalid input renders "—". */
export function formatClock(iso?: string | null): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleTimeString("zh-CN", { hour12: false });
}

export type ChangeTone = "up" | "down" | "flat";

export function changeTone(value?: number | null): ChangeTone {
  if (value == null || !Number.isFinite(value) || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

export type IntegrityTone = "ok" | "warn" | "danger";

export function integrityTone(status?: DataIntegrity["status"] | null): IntegrityTone {
  if (status === "ok") return "ok";
  if (status === "fail") return "danger";
  return "warn";
}

export function integrityLabel(status?: DataIntegrity["status"] | null): string {
  if (status === "ok") return "体检通过";
  if (status === "fail") return "体检失败";
  if (status === "warn") return "体检有警告";
  return "体检未运行";
}

export interface MarketReadings {
  price: number | null;
  change: number | null;
  changePct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  preClose: number | null;
  volume: number | null;
  amount: number | null;
  turnoverPct: number | null;
  amplitudePct: number | null;
  limitUp: number | null;
  limitDown: number | null;
  suspended: boolean;
  updatedAt: string | null;
  source: "live" | "snapshot" | "none";
}

/** Right-hand quote readings: live quote first, local snapshot bars/profile fallback. */
export function marketReadings(input: { quote?: LiveQuote | null; bars?: Bars | null; profile?: SecurityProfile | null }): MarketReadings {
  const { quote, bars, profile } = input;
  if (quote) {
    const preClose = quote.prev_close || null;
    const amplitude = quote.high != null && quote.low != null && preClose
      ? ((quote.high - quote.low) / preClose) * 100
      : null;
    return {
      price: quote.price,
      change: quote.change,
      changePct: quote.change_pct,
      open: quote.open,
      high: quote.high,
      low: quote.low,
      preClose,
      volume: quote.volume,
      amount: quote.amount,
      turnoverPct: quote.turnover_pct,
      amplitudePct: amplitude,
      limitUp: quote.limit_up,
      limitDown: quote.limit_down,
      suspended: quote.suspended,
      updatedAt: quote.timestamp,
      source: "live",
    };
  }
  const lastIndex = bars?.close.length ? bars.close.length - 1 : -1;
  const close = lastIndex >= 0 ? bars!.close[lastIndex] : profile?.quote.close ?? null;
  const preClose = lastIndex > 0 ? bars!.close[lastIndex - 1] : profile?.quote.pre_close ?? null;
  const high = lastIndex >= 0 ? bars!.high[lastIndex] : profile?.quote.high ?? null;
  const low = lastIndex >= 0 ? bars!.low[lastIndex] : profile?.quote.low ?? null;
  const change = close != null && preClose != null ? close - preClose : null;
  const changePct = profile?.quote.change_pct ?? (change != null && preClose ? (change / preClose) * 100 : null);
  const amplitude = high != null && low != null && preClose ? ((high - low) / preClose) * 100 : null;
  return {
    price: close,
    change,
    changePct,
    open: lastIndex >= 0 ? bars!.open[lastIndex] : profile?.quote.open ?? null,
    high,
    low,
    preClose,
    volume: lastIndex >= 0 ? bars!.volume[lastIndex] : profile?.quote.volume ?? null,
    amount: lastIndex >= 0 ? bars!.amount[lastIndex] : profile?.quote.amount ?? null,
    turnoverPct: lastIndex >= 0 ? bars!.turnover[lastIndex] : profile?.quote.turnover ?? null,
    amplitudePct: amplitude,
    limitUp: lastIndex >= 0 ? bars!.limit_up[lastIndex] : null,
    limitDown: lastIndex >= 0 ? bars!.limit_down[lastIndex] : null,
    suspended: Boolean(lastIndex >= 0 ? bars!.suspended[lastIndex] : profile?.quote.suspended),
    updatedAt: profile?.quote.date ? String(profile.quote.date) : bars?.dates.length ? bars.dates[bars.dates.length - 1] : null,
    source: close != null ? "snapshot" : "none",
  };
}

export function updatedAtLabel(readings: MarketReadings): string {
  if (readings.source === "live") return formatClock(readings.updatedAt);
  if (!readings.updatedAt) return "—";
  return dateInt(readings.updatedAt);
}
