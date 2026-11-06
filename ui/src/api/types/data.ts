/** UI-API v2 data payload types. */

export interface DatasetInfo {
  name: string;
  version: string;
  grain: string;
  storage: string;
  synthetic: boolean | null;
  fields: string[];
  description: string;
}

export interface DatasetCatalog {
  version: string;
  datasets: DatasetInfo[];
  notes: string[];
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
  start: number | string;
  end: number | string;
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

export interface IntegrityCheckView {
  id: string;
  title: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface DataIntegrity {
  status: "ok" | "warn" | "fail";
  generated_at: string;
  snapshot: {
    id: string;
    synthetic: boolean;
    source: string;
    n_sec: number;
    n_time: number;
    start: number;
    end: number;
  } | null;
  coverage: {
    expected_cells: number;
    present_cells: number;
    coverage_pct: number;
    symbols: number;
    trading_days: number;
  };
  checks: IntegrityCheckView[];
  gaps: {
    missing_days: number;
    symbols_with_gaps: number;
    examples: Array<{ code: string; date: number }>;
  };
  accuracy: {
    ohlc_violations: number;
    volume_amount_mismatch: number;
    limit_violations: number;
    adjustment_breaks: number;
  };
  cross_source: {
    checked: number;
    matched: number;
    max_rel_diff: number | null;
    source: string | null;
    note: string;
  };
  note: string;
}

export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  action: "bootstrap" | "backtest" | "browse" | "data";
  label: string;
  done: boolean;
}

export interface OnboardingState {
  first_run: boolean;
  beginner: boolean;
  steps: OnboardingStep[];
  progress: { done: number; total: number };
}
