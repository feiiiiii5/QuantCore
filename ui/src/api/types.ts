/** UI-API v2 response types. Keep this file the single source of payload shapes. */

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface JsonSchema {
  title?: string;
  description?: string;
  type?: string;
  default?: unknown;
  enum?: unknown[];
  minimum?: number;
  maximum?: number;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
}

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

export interface Template {
  id: string;
  name?: string;
  description: string;
  params_schema: JsonSchema;
}

export interface ValidationResult {
  valid: boolean;
  errors: unknown[];
  defaults: Record<string, unknown>;
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
  calmar?: number;
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

export interface JobResult {
  run_id?: string;
  engine_backend?: string;
  engine_version?: string;
  metrics?: Metrics;
  trade_count?: number;
  final_equity?: number;
  snapshot?: Record<string, unknown>;
  synthetic?: boolean;
  report?: string;
  experiments_root?: string;
  [key: string]: unknown;
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
  result: JobResult | null;
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

export interface ExperimentDetail {
  run_id: string;
  metadata: Record<string, unknown>;
  summary: Record<string, unknown>;
  metrics: Metrics;
  result?: BacktestResultPayload | null;
}

export interface CompareResult {
  ids: string[];
  metrics: Record<string, Metrics>;
  equity: Array<{ run_id: string; dates: number[]; equity: number[] }>;
}

export interface ReplayResult {
  run_id?: string;
  matched?: boolean;
  equity_matched?: boolean;
  trades_matched?: boolean;
  metrics_matched?: boolean;
  differences?: unknown;
  diffs?: unknown;
  [key: string]: unknown;
}

export interface ProviderInfo {
  id: string;
  name: string;
  requires_token: boolean;
  requires_network: boolean;
  available: boolean;
  capabilities: Record<string, boolean>;
}

export interface SnapshotStatus {
  id: string;
  content_hash: string;
  created_at: string;
  synthetic: boolean;
  source: string;
  n_sec: number;
  n_time: number;
  start: number;
  end: number;
  panel_available: boolean;
  quality: Record<string, unknown>;
  fields: string[];
}

export interface DataStatus {
  data_root: string;
  warehouse: { exists: boolean; datasets: Record<string, number>; rows: number; bytes: number; manifest_hash: string };
  snapshots: SnapshotStatus[];
  storage: { warehouse_bytes: number; snapshot_bytes: number; experiments_bytes: number; free_bytes: number };
  providers: ProviderInfo[];
}

export interface QualityReport {
  snapshot_id: string;
  quality: Record<string, unknown>;
  report?: Record<string, unknown>;
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
  decay: Array<{ days: number; ic?: number | null; rank_ic: number | null }>;
  coverage: number;
  observations: number;
}

export interface SweepPoint {
  params: Record<string, unknown>;
  metrics: Metrics;
  error: string | null;
}

export interface SweepResult {
  template?: string;
  points: SweepPoint[];
  best: { params: Record<string, unknown>; metrics: Metrics } | null;
  engine_backend: string;
  bounded_points?: number;
  grid_size?: number;
  sampling?: { mode: "grid" | "random"; requested: number; returned: number; seed: number };
  synthetic?: boolean;
}

export interface FactorCorrelationResult {
  expressions: string[];
  labels: string[];
  matrix: number[][];
  average_abs_correlation: number;
  observations: number;
  periods: number;
  dates: number[];
  method: "pearson" | "spearman";
  note: string;
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
  industries: Array<{
    industry: string;
    pnl: number;
    realized: number;
    unrealized?: number;
    market_value?: number;
    weight?: number;
    securities?: number;
  }>;
}

export interface PaperSessionSummary {
  id: string;
  name: string;
  status: string;
  snapshot: string | null;
  snapshot_meta?: Record<string, unknown>;
  current_date: number;
  start_date: number;
  end_date: number;
  cash: number;
  equity: number;
  starting_cash: number;
  position_count: number;
  pending_orders: number;
  synthetic: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaperAccount {
  cash: number;
  market_value: number;
  equity: number;
  pnl: number;
  pnl_pct: number;
}

export interface PaperPosition {
  sec_id: string;
  code: string;
  name: string;
  board: string;
  qty: number;
  available: number;
  avg_cost: number;
  last: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
}

export interface PaperOrder {
  id: string;
  date: number;
  code: string;
  sec_id: string;
  name: string;
  side: "buy" | "sell";
  qty: number;
  order_type: "market" | "limit";
  limit_price: number | null;
  status: string;
  filled_qty: number;
  fill_price: number | null;
  fill_date: number | null;
  fees: Record<string, number> | null;
  reason: string | null;
  created_at: string;
}

export interface PaperTrade {
  id: string;
  order_id: string;
  date: number;
  code: string;
  sec_id: string;
  name: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  amount: number;
  fee_total: number;
  fees: Record<string, number>;
  created_at: string;
}

export interface PaperSessionDetail {
  session: PaperSessionSummary;
  snapshot: Record<string, unknown>;
  account: PaperAccount;
  positions: PaperPosition[];
  orders: PaperOrder[];
  trades: PaperTrade[];
  equity_curve: Array<{ date: number; equity: number }>;
  fills?: Array<Record<string, unknown>>;
}

export interface OverfittingResult {
  run_id: string;
  observations: number;
  periods_per_year: number;
  sharpe: number;
  deflated_sharpe: number;
  expected_max_sharpe: number;
  n_trials: number;
  skew: number;
  kurtosis: number;
  verdict: "robust" | "inconclusive" | "likely_overfit" | string;
}

export interface PBOResult {
  run_ids: string[];
  n_splits: number;
  combinations: number;
  pbo: number;
  median_oos_rank: number;
  logits: number[][];
}

export interface CostSensitivityPoint {
  multiplier: number;
  total_return: number;
  annualized_return: number;
  sharpe: number;
  max_drawdown: number;
  total_fees: number;
}

export interface CostSensitivityResult {
  run_id: string;
  points: CostSensitivityPoint[];
  breakeven_multiplier: number | null;
}

export interface MonteCarloResult {
  run_id: string;
  n_paths: number;
  horizon: number;
  terminal_return: { p05: number; p25: number; p50: number; p75: number; p95: number };
  max_drawdown: { p05: number; p50: number; p95: number };
  paths: number[][];
}

export interface CapacityResult {
  run_id: string;
  capacity_cny: number;
  participation: number;
  avg_turnover: number;
  avg_adv_cny: number;
  limiting_sec: string;
  notes: string;
}

export interface PluginIssue {
  severity: string;
  message: string;
  line: number;
}

export interface PluginInfo {
  name: string;
  path: string;
  bytes: number;
  updated_at: string;
  valid: boolean;
  issues: PluginIssue[];
  interface: string;
  description: string | null;
  version: string | null;
}

export interface PluginValidation extends Omit<PluginInfo, "path" | "bytes" | "updated_at"> {
  path: string;
  policy: Record<string, unknown>;
}

export interface PluginBacktestAccepted {
  job_id: string;
  status: string;
  plugin: string;
}
