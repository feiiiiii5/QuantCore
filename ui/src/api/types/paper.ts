/** UI-API v2 paper payload types. */

export interface PaperSessionSummary {
  id: string;
  mode?: "historical" | "live";
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
  quote_timestamp?: string | null;
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

export interface PaperCorporateEvent {
  date: number;
  code: string;
  sec_id: string;
  cash: number;
  qty_before: number;
  qty_after: number;
  cancelled_order_ids: string[];
  reason: string;
  model: "pre_tax_ex_date_approximation";
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
  corporate_events?: PaperCorporateEvent[];
  live?: {
    state: string;
    as_of: string | null;
    notice: string;
    quotes: Array<{ code: string; timestamp: string | null; reason: string | null; price: number | null }>;
  };
}

export interface PaperAutoStatus {
  session_id: string;
  running: boolean;
  ticks?: number;
  error?: string | null;
  interval_ms?: number;
  days_per_tick?: number;
}

export interface PaperPortfolioAllocation {
  session_id: string;
  name: string;
  snapshot: string | null;
  synthetic: boolean;
  weight: number;
}

export interface PaperPortfolioResult {
  allocations: PaperPortfolioAllocation[];
  dates: number[];
  equity: number[];
  normalized_equity?: number[];
  metrics: {
    total_return: number;
    annualized_return: number;
    volatility: number;
    sharpe: number;
    max_drawdown: number;
  };
  contributions: Array<{
    session_id: string;
    name: string;
    weight: number;
    total_return: number;
    contribution: number;
  }>;
  note: string;
}
