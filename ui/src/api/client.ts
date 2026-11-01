import type {
  BacktestResultPayload, Bars, DataStatus, Experiment, FactorResult, Health, Job, MarketOverview, Meta,
  ScreenerResult, SecurityRow, SnapshotInfo, SweepResult, Template, WalkForwardResult, AttributionResult,
} from "./types";

const API_KEY = "qc_api";
const TOKEN_KEY = "qc_token";

export function getApiBase(): string {
  const stored = localStorage.getItem(API_KEY);
  if (stored) return stored.replace(/\/+$/, "");
  const origin = window.location.origin;
  return origin.startsWith("http") ? origin : "";
}
export function getToken(): string { return localStorage.getItem(TOKEN_KEY) || ""; }
export function configure(base: string, token: string): void {
  localStorage.setItem(API_KEY, base.replace(/\/+$/, ""));
  localStorage.setItem(TOKEN_KEY, token);
}
export function wsUrl(jobId: string): string {
  const base = getApiBase() || window.location.origin;
  const url = new URL(base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/jobs/${jobId}`;
  url.search = `?token=${encodeURIComponent(getToken())}`;
  return url.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try { const body = await res.json(); detail = body.detail || body.message || JSON.stringify(body); } catch { /* plain text */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  meta: () => request<Meta>("/api/meta"),
  overview: (snapshot?: string) => request<MarketOverview>(`/api/market/overview${snapshot ? `?snapshot=${encodeURIComponent(snapshot)}` : ""}`),
  bars: (code: string, snapshot?: string) => request<Bars>(`/api/market/bars?code=${encodeURIComponent(code)}${snapshot ? `&snapshot=${encodeURIComponent(snapshot)}` : ""}`),
  securities: (query = "", limit = 200) => request<SecurityRow[]>(`/api/market/securities?query=${encodeURIComponent(query)}&limit=${limit}`),
  screenerPresets: () => request<Array<{ id: string; name: string; description: string; expression: string }>>("/api/screener/presets"),
  runScreener: (payload: { expression: string; universe?: Record<string, unknown>; limit?: number }) =>
    request<ScreenerResult>("/api/screener/run", { method: "POST", body: JSON.stringify(payload) }),
  templates: () => request<Template[]>("/api/strategies/templates"),
  validateStrategy: (template: string, params: Record<string, unknown>) =>
    request<{ valid: boolean; errors: unknown[]; defaults: Record<string, unknown> }>("/api/strategies/validate", { method: "POST", body: JSON.stringify({ template, params }) }),
  submitBacktest: (payload: Record<string, unknown>) => request<{ job_id: string; status: string }>("/api/backtest", { method: "POST", body: JSON.stringify(payload) }),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => request<{ job_id: string; cancelled: boolean; status: string }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  experiments: () => request<Experiment[]>("/api/experiments"),
  experiment: (id: string) => request<Record<string, unknown>>(`/api/experiments/${id}`),
  experimentResult: (id: string) => request<BacktestResultPayload>(`/api/experiments/${id}/result`),
  replayExperiment: (id: string) => request<Record<string, unknown>>(`/api/experiments/${id}/replay`, { method: "POST" }),
  dataStatus: () => request<DataStatus>("/api/data/status"),
  snapshots: () => request<SnapshotInfo[]>("/api/data/snapshots"),
  updateData: (payload: Record<string, unknown>) => request<{ job_id: string; status: string }>("/api/data/update", { method: "POST", body: JSON.stringify(payload) }),
  buildSnapshot: () => request<{ job_id: string; status: string }>("/api/data/snapshot", { method: "POST", body: JSON.stringify({ require_qpanel: true }) }),
  bootstrap: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/api/onboarding/bootstrap", { method: "POST", body: JSON.stringify(payload) }),
  factor: (payload: Record<string, unknown>) => request<FactorResult>("/api/research/factor", { method: "POST", body: JSON.stringify(payload) }),
  sweep: (payload: Record<string, unknown>) => request<SweepResult>("/api/research/sweep", { method: "POST", body: JSON.stringify(payload) }),
  walkForward: (payload: Record<string, unknown>) => request<WalkForwardResult>("/api/research/walk_forward", { method: "POST", body: JSON.stringify(payload) }),
  attribution: (runId: string) => request<AttributionResult>("/api/research/attribution", { method: "POST", body: JSON.stringify({ run_id: runId }) }),
};
