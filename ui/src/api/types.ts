export interface PanelInfo {
  n_sec: number;
  n_time: number;
  dates: number[];
  fields: string[];
}

export interface Metrics {
  total_return: number;
  annualized_return: number;
  volatility: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  turnover: number;
  total_fees: number;
  trade_count: number;
}

export interface BacktestRequest {
  snapshot: string;
  strategy: string;
  params?: Record<string, unknown>;
  start?: string;
  end?: string;
  initial_cash?: number;
}

export interface BacktestResult {
  engine_version: string;
  dates: number[];
  equity: number[];
  cash: number[];
  market_value: number[];
  metrics: Metrics;
  trades: Array<Record<string, unknown>>;
  reasons?: Record<string, number>;
}

export interface Health {
  status: string;
  version: string;
  engine_backend: string;
}
