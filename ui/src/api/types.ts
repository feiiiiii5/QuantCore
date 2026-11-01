export interface Health {
  status: string;
  version: string;
  engine_backend: string;
  engine_available: boolean;
  panel_available: boolean;
  synthetic_only: boolean;
  cors: boolean;
}

export interface Meta {
  version: string;
  engine_backend: string;
  synthetic_only: boolean;
  data_root: string;
  snapshots_root: string;
  experiments_root: string;
  token_required: boolean;
  ui_served: boolean;
  cors: boolean;
}

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

export interface MarketOverview {
  snapshot: SnapshotInfo;
  indices: IndexQuote[];
  breadth: { up: number; down: number; flat: number; limit_up: number; limit_down: number; suspended: number };
  sectors: Array<{ name: string; count: number; avg_change: number; up: number; down: number }>;
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
  amount: number[];
  turnover: number[];
  ma5: Array<number | null>;
  ma20: Array<number | null>;
  limit_up: number[];
  limit_down: number[];
  suspended: number[];
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
  snapshot: string;
  universe_count: number;
  matched_count: number;
  rows: ScreenerRow[];
}

export interface Template {
  id: string;
  description: string;
  params_schema: {
    properties?: Record<string, { title?: string; type?: string; default?: unknown; minimum?: number; maximum?: number; enum?: unknown[]; anyOf?: unknown[] }>;
    required?: string[];
  };
}

export interface Metrics {
  total_return: number;
  annualized_return: number;
  volatility?: number;
  sharpe: number;
  sortino?: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor?: number | null;
  turnover: number;
  total_fees: number;
  trade_count: number;
  trading_days?: number;
}

export interface Trade {
  date: number;
  sec_index?: number;
  sec_id?: string;
  side: number;
  side_name?: string;
  px?: number;
  px_yuan?: number;
  qty: number;
  amount?: number;
  amount_yuan?: number;
  fee_total?: number;
  commission?: number;
  stamp_duty?: number;
  transfer_fee?: number;
  other_fee?: number;
  reason?: number;
  reason_name?: string;
}

export interface BacktestResultPayload {
  dates: number[];
  equity: number[];
  cash: number[];
  market_value: number[];
  trades: Trade[];
  metrics: Metrics;
  reasons: Record<string, number>;
  engine_backend: string;
  engine_version: string;
  seed: number;
}

export interface Job {
  id: string;
  kind: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface Experiment {
  run_id: string;
  kind: string;
  created_at: string;
  status: string;
  strategy_name: string | null;
  template: string | null;
  snapshot_id: string | null;
  content_hash: string | null;
  metrics: Metrics | null;
  tags: string[];
  note: string;
  synthetic: boolean;
}

export interface DataStatus {
  data_root: string;
  warehouse: { exists: boolean; datasets: Record<string, number>; rows: number; bytes: number; manifest_hash: string };
  snapshots: Array<{
    id: string; content_hash: string; created_at: string; synthetic: boolean; source: string;
    n_sec: number; n_time: number; start: number; end: number; panel_available: boolean;
    quality: Record<string, unknown>; fields: string[];
  }>;
  storage: { warehouse_bytes: number; snapshot_bytes: number; experiments_bytes: number; free_bytes: number };
  providers: Array<Record<string, unknown>>;
}

export interface FactorResult {
  name: string;
  expression?: string;
  synthetic?: boolean;
  forward_days?: number;
  quantiles?: number;
  ic_mean: number;
  rank_ic_mean: number;
  icir: number | null;
  rank_icir: number | null;
  ic_series: Array<{ date: number; ic: number | null; rank_ic: number | null }>;
  quantile_returns: Array<{ bucket: number; mean_return: number | null; observations: number }>;
  decay: Array<{ days: number; rank_ic: number | null }>;
  coverage: number;
  observations: number;
}

export interface SweepResult {
  template?: string;
  points: Array<{ params: Record<string, unknown>; metrics: Record<string, number>; error: string | null }>;
  best: { params: Record<string, unknown>; metrics: Record<string, number> } | null;
  engine_backend: string;
  bounded_points?: number;
  synthetic?: boolean;
}

export interface WalkForwardFold {
  fold: number;
  start: number;
  end: number;
  trading_days: number;
  trade_count: number;
  metrics: Metrics;
}

export interface WalkForwardResult {
  template: string;
  params: Record<string, unknown>;
  engine_backend: string;
  folds: WalkForwardFold[];
  aggregate?: Metrics;
  synthetic?: boolean;
}

export interface AttributionResult {
  run_id: string;
  strategy_name?: string | null;
  synthetic?: boolean;
  industries: Array<{ industry: string; pnl: number; realized: number; unrealized?: number; market_value?: number; weight?: number; securities?: number }>;
}
