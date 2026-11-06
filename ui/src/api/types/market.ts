/** UI-API v2 market payload types. */

export interface SnapshotInfo {
  id: string | null;
  content_hash: string | null;
  n_sec: number | null;
  n_time: number | null;
  start: string | null;
  end: string | null;
  synthetic: boolean;
  source: string | null;
  fields: string[];
}

export interface IndexQuote {
  name: string;
  close: number;
  change_pct: number;
  spark: number[];
}

export interface MarketBreadth {
  up: number;
  down: number;
  flat: number;
  limit_up: number;
  limit_down: number;
  suspended: number;
}

export interface SectorRow {
  name: string;
  count: number;
  avg_change: number;
  up: number;
  down: number;
}

export interface MarketOverview {
  snapshot: SnapshotInfo;
  indices: IndexQuote[];
  breadth: MarketBreadth;
  sectors: SectorRow[];
  as_of: string | null;
  updated_at: string;
}

export interface SecurityRow {
  sec_id: string;
  code: string;
  name: string;
  board: string;
  industry: string;
  last: number;
  change_pct: number;
  turnover: number;
  mktcap: number;
  float_mktcap: number;
  suspended: boolean;
  st: boolean;
  exchange?: string;
  sec_type?: string;
  list_date?: number;
  delist_date?: number;
  source?: string;
}

export interface SecurityProfile {
  sec_id: string;
  code: string;
  name: string;
  exchange: string;
  board: string;
  sec_type: string;
  industry: string;
  source: string;
  list_date: number;
  delist_date: number;
  quote: {
    date: number;
    close: number;
    pre_close: number;
    change_pct: number;
    open: number;
    high: number;
    low: number;
    volume: number;
    amount: number;
    turnover: number;
    st: boolean;
    suspended: boolean;
  };
}

export interface Bars {
  code: string;
  name: string;
  board: string;
  dates: string[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
  amount: Array<number | null>;
  turnover: Array<number | null>;
  ma5: Array<number | null>;
  ma20: Array<number | null>;
  limit_up: number[];
  limit_down: number[];
  suspended: number[];
  source?: string;
  synthetic?: boolean;
  as_of?: string | null;
  note?: string;
}

export interface MinuteBar {
  datetime: number;
  date: number;
  sec_id: string;
  code: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  source: string;
}

export interface MinuteBars {
  code: string;
  date: number | null;
  synthetic: boolean;
  source: string;
  snapshot: string | null;
  bars: MinuteBar[];
}

export interface ScreenerPreset {
  id: string;
  name: string;
  description: string;
  expression: string;
}

export interface ScreenerRow {
  sec_id: string;
  code: string;
  name: string;
  board: string;
  industry: string;
  close: number;
  change_pct: number;
  turnover: number;
  mktcap: number;
  score: number;
}

export interface ScreenerResult {
  as_of: number;
  snapshot: string | null;
  universe_count: number;
  matched_count: number;
  rows: ScreenerRow[];
}

export interface ScreenerSaved {
  id: string;
  name: string;
  expression: string;
  created_at: string;
}

export interface FinancialReport {
  sec_id: string;
  end_date: number;
  ann_date: number;
  f_ann_date: number;
  report_type: string;
  revenue: number | null;
  net_profit: number | null;
  total_assets: number | null;
  total_equity: number | null;
  roe: number | null;
  eps: number | null;
  bps: number | null;
  dividend_per_share: number | null;
  source: string;
}

export interface FinancialsResult {
  code: string;
  sec_id: string;
  as_of: string | null;
  latest: FinancialReport | null;
  rows: FinancialReport[];
  note: string;
}

// ---------------------------------------------------------------- live market / 新手流程（重构轮）

/** Where an endpoint or helper lives for the live quote service. */
export type LiveState = "off" | "idle" | "connecting" | "live" | "error" | "closed";

export type MarketPhase = "pre_open" | "open" | "lunch" | "closed" | "holiday";

export interface MarketClock {
  phase: MarketPhase;
  is_trading_day: boolean;
  server_time: string;
  next_open: string | null;
  last_trade_date: number | null;
}

export interface LiveStatus {
  enabled: boolean;
  source: "eastmoney" | "sina" | "none";
  state: LiveState;
  market: MarketClock;
  as_of: string | null;
  latency_ms: number | null;
  subscribed: number;
  error: string | null;
  notice: string;
}

export interface LiveQuote {
  code: string;
  name: string;
  price: number;
  prev_close: number;
  open: number | null;
  high: number | null;
  low: number | null;
  change: number;
  change_pct: number;
  volume: number;
  amount: number;
  turnover_pct: number | null;
  limit_up: number | null;
  limit_down: number | null;
  suspended: boolean;
  timestamp: string | null;
  source: string;
  stale?: boolean;
  received_at?: string | null;
}

export interface LiveQuotesPayload {
  as_of: string | null;
  source: string;
  stale: boolean;
  quotes: LiveQuote[];
}

export interface WatchlistPayload {
  codes: string[];
}
