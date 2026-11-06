/** UI-API v2 research payload types. */

import type { JsonSchema } from "./core";

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
  benchmark_return?: number;
  excess_return?: number | null;
  tracking_error?: number | null;
  information_ratio?: number | null;
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
  config?: Record<string, unknown>;
  snapshot?: ExperimentSnapshotMetadata;
  synthetic?: boolean | null;
  benchmark?: {
    code: string;
    sec_id: string;
    name: string;
    dates: number[];
    equity: Array<number | null>;
    total_return: number;
    daily_observations?: number;
    complete_window?: boolean;
    definition?: string;
    metrics: Record<string, number | null>;
  } | null;
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
  metadata: ExperimentMetadata;
  summary: Record<string, unknown>;
  metrics: Metrics;
  result?: BacktestResultPayload | null;
}

export interface ExperimentMetadata extends Record<string, unknown> {
  parent_run_id?: string;
  strategy_name?: string;
  strategy_hash?: string;
  strategy?: { template?: string; params?: Record<string, unknown> };
  config?: Record<string, unknown>;
  snapshot?: ExperimentSnapshotMetadata;
  environment?: { git_commit?: string };
  engine_backend?: string;
  engine_version?: string;
  synthetic?: boolean;
}

export interface ExperimentSnapshotMetadata extends Record<string, unknown> {
  snapshot_id?: string | null;
  content_hash?: string;
  source?: string;
  synthetic?: boolean;
}

export interface ExperimentProvenance {
  parent_run_id?: string | null;
  strategy_name: string | null;
  template: string | null;
  strategy_hash: string | null;
  params: Record<string, unknown>;
  snapshot_id: string | null;
  content_hash: string | null;
  source: string | null;
  synthetic: boolean | null;
  config: Record<string, unknown>;
  engine_backend: string | null;
  engine_version: string | null;
  git_commit: string | null;
}

export type ComparisonStatus = "matched" | "different" | "unknown";

export interface ComparisonDimension {
  key: string;
  label: string;
  status: ComparisonStatus;
  values: Record<string, unknown>;
}

export interface CompareResult {
  ids: string[];
  metrics: Record<string, Metrics>;
  equity: Array<{
    run_id: string;
    dates: number[];
    equity: number[];
    label: string;
    initial_cash: number | null;
    normalized_equity: number[] | null;
    drawdown: number[];
    provenance: ExperimentProvenance;
  }>;
  comparison: {
    status: ComparisonStatus;
    dimensions: ComparisonDimension[];
    warnings: Array<{ code: string; message: string }>;
  };
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

export interface StrategyPreset {
  id: string;
  name: string;
  tagline: string;
  description: string;
  plain_terms: string;
  risk_note: string;
  template: string;
  params: Record<string, unknown>;
  horizon: string;
  suitable_for: string;
}
