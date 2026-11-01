import type {
  MinuteBars,
  AttributionResult, BacktestResultPayload, Bars, CompareResult, DataStatus, Experiment, ExperimentDetail,
  FactorCorrelationResult, FactorResult, FinancialsResult, Health, Job, JobResult, MarketOverview, Meta, ProviderInfo, QualityReport, ReplayResult,
  CapacityResult, CostSensitivityResult, MonteCarloResult, OverfittingResult, PaperAutoStatus, PaperOrder, PaperPortfolioResult,
  PaperSessionDetail, PaperSessionSummary, PBOResult, PluginBacktestAccepted, PluginInfo, PluginValidation,
  ScreenerPreset, ScreenerResult, ScreenerSaved, SecurityProfile, SecurityRow, SnapshotInfo, SnapshotStatus, SweepResult,
  Template, ValidationResult, WalkForwardResult,
} from "./types";

const API_KEY = "qc_api";
const TOKEN_KEY = "qc_token";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  constructor(status: number, message: string, detail: unknown = message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Same-origin by default; set a base in Settings for a split dev/preview origin. */
export function getApiBase(): string {
  return (localStorage.getItem(API_KEY) || "").replace(/\/+$/, "");
}
export function getToken(): string { return localStorage.getItem(TOKEN_KEY) || ""; }

export function configure(base: string, token: string): void {
  localStorage.setItem(API_KEY, base.trim().replace(/\/+$/, ""));
  localStorage.setItem(TOKEN_KEY, token.trim());
}

export function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function wsUrl(jobId: string): string {
  const base = getApiBase() || window.location.origin;
  const url = new URL(base, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/jobs/${encodeURIComponent(jobId)}`;
  url.search = `?token=${encodeURIComponent(getToken())}`;
  return url.toString();
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) return String(item.msg);
      return JSON.stringify(item);
    }).join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  for (const [key, value] of Object.entries(authHeaders())) headers.set(key, value);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  } catch (error) {
    throw new ApiError(0, `无法连接本地服务：${error instanceof Error ? error.message : "network error"}`);
  }
  if (!response.ok) {
    let detail: unknown = `${response.status} ${response.statusText}`;
    try { detail = await response.json(); } catch { /* non-JSON error body */ }
    const body = detail && typeof detail === "object" && "detail" in detail ? (detail as { detail: unknown }).detail : detail;
    throw new ApiError(response.status, detailMessage(body, response.statusText), body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function downloadWithAuth(path: string, filename: string): Promise<void> {
  const response = await fetch(`${getApiBase()}${path}`, { headers: authHeaders() });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = detailMessage((await response.json() as { detail?: unknown }).detail, detail); } catch { /* ignore */ }
    throw new ApiError(response.status, detail);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const api = {
  health: () => request<Health>("/health"),
  meta: () => request<Meta>("/api/meta"),

  overview: (snapshot?: string) => request<MarketOverview>(`/api/market/overview${snapshot ? `?snapshot=${encodeURIComponent(snapshot)}` : ""}`),
  bars: (code: string, snapshot?: string) => request<Bars>(`/api/market/bars?code=${encodeURIComponent(code)}${snapshot ? `&snapshot=${encodeURIComponent(snapshot)}` : ""}`),
  securities: (query = "", limit = 300) => request<SecurityRow[]>(`/api/market/securities?query=${encodeURIComponent(query)}&limit=${limit}`),
  minuteBars: (code: string, date?: string) => request<MinuteBars>(`/api/market/minute-bars?code=${encodeURIComponent(code)}${date ? `&date=${encodeURIComponent(date)}` : ""}`),
  financials: (code: string, asOf?: string) => request<FinancialsResult>(`/api/market/financials/${encodeURIComponent(code)}${asOf ? `?as_of=${encodeURIComponent(asOf)}` : ""}`),
  securityProfile: (code: string, snapshot?: string) => request<SecurityProfile>(`/api/market/securities/${encodeURIComponent(code)}${snapshot ? `?snapshot=${encodeURIComponent(snapshot)}` : ""}`),

  screenerPresets: () => request<ScreenerPreset[]>("/api/screener/presets"),
  runScreener: (payload: { expression: string; universe?: Record<string, unknown>; limit?: number }) =>
    request<ScreenerResult>("/api/screener/run", { method: "POST", body: JSON.stringify(payload) }),
  savedScreeners: () => request<ScreenerSaved[]>("/api/screener/saved"),
  saveScreener: (payload: { name: string; expression: string }) =>
    request<ScreenerSaved>("/api/screener/saved", { method: "POST", body: JSON.stringify(payload) }),
  deleteSavedScreener: (id: string) => request<{ id: string; deleted: boolean }>(`/api/screener/saved/${encodeURIComponent(id)}`, { method: "DELETE" }),

  templates: () => request<Template[]>("/api/strategies/templates"),
  validateStrategy: (template: string, params: Record<string, unknown>) =>
    request<ValidationResult>("/api/strategies/validate", { method: "POST", body: JSON.stringify({ template, params }) }),

  submitBacktest: (payload: Record<string, unknown>) => request<{ job_id: string; status: string }>("/api/backtest", { method: "POST", body: JSON.stringify(payload) }),
  jobs: (status?: string, limit = 50) => request<Job[]>(`/api/jobs?${status ? `status=${encodeURIComponent(status)}&` : ""}limit=${limit}`),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  jobResult: (id: string) => request<{ job_id: string; status: string; result?: JobResult }>(`/api/jobs/${encodeURIComponent(id)}/result`),
  cancelJob: (id: string) => request<{ job_id: string; cancelled: boolean; status: string }>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),

  experiments: (limit = 100) => request<Experiment[]>(`/api/experiments?limit=${limit}`),
  experiment: (id: string) => request<ExperimentDetail>(`/api/experiments/${encodeURIComponent(id)}`),
  experimentResult: (id: string) => request<BacktestResultPayload>(`/api/experiments/${encodeURIComponent(id)}/result`),
  compareExperiments: (ids: string[]) => request<CompareResult>(`/api/experiments/compare?ids=${ids.map(encodeURIComponent).join(",")}`),
  replayExperiment: (id: string) => request<ReplayResult>(`/api/experiments/${encodeURIComponent(id)}/replay`, { method: "POST" }),
  deleteExperiment: (id: string) => request<{ run_id: string; deleted: boolean }>(`/api/experiments/${encodeURIComponent(id)}`, { method: "DELETE" }),

  dataStatus: () => request<DataStatus>("/api/data/status"),
  providers: () => request<ProviderInfo[]>("/api/data/providers"),
  snapshots: () => request<SnapshotStatus[]>("/api/data/snapshots"),
  quality: (snapshot: string) => request<QualityReport>(`/api/data/quality?snapshot=${encodeURIComponent(snapshot)}`),
  updateData: (payload: Record<string, unknown>) => request<{ job_id: string; status: string }>("/api/data/update", { method: "POST", body: JSON.stringify(payload) }),
  buildSnapshot: () => request<{ job_id: string; status: string }>("/api/data/snapshot", { method: "POST", body: JSON.stringify({ require_qpanel: true }) }),
  bootstrap: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/api/onboarding/bootstrap", { method: "POST", body: JSON.stringify(payload) }),

  plugins: () => request<PluginInfo[]>("/api/strategies/plugins"),
  validatePlugin: (name: string) => request<PluginValidation>(`/api/strategies/plugins/${encodeURIComponent(name)}/validate`, { method: "POST" }),
  runPlugin: (name: string, payload: Record<string, unknown>) =>
    request<PluginBacktestAccepted>(`/api/strategies/plugins/${encodeURIComponent(name)}/backtest`, { method: "POST", body: JSON.stringify(payload) }),
  paperPortfolio: (payload: Record<string, unknown>) =>
    request<PaperPortfolioResult>("/api/paper/portfolio", { method: "POST", body: JSON.stringify(payload) }),
  startPaperAuto: (id: string, intervalMs = 1000) =>
    request<PaperAutoStatus>(`/api/paper/sessions/${id}/auto`, { method: "POST", body: JSON.stringify({ interval_ms: intervalMs, days_per_tick: 1 }) }),
  stopPaperAuto: (id: string) =>
    request<PaperAutoStatus>(`/api/paper/sessions/${id}/auto/stop`, { method: "POST" }),
  paperAutoStatus: (id: string) => request<PaperAutoStatus>(`/api/paper/sessions/${id}/auto`),
  paperSessions: () => request<PaperSessionSummary[]>("/api/paper/sessions"),
  createPaperSession: (payload: Record<string, unknown>) =>
    request<PaperSessionSummary>("/api/paper/sessions", { method: "POST", body: JSON.stringify(payload) }),
  paperSession: (id: string) => request<PaperSessionDetail>(`/api/paper/sessions/${id}`),
  stepPaper: (id: string, days = 1) =>
    request<PaperSessionDetail>(`/api/paper/sessions/${id}/step`, { method: "POST", body: JSON.stringify({ days }) }),
  resetPaper: (id: string) =>
    request<PaperSessionDetail>(`/api/paper/sessions/${id}/reset`, { method: "POST" }),
  submitPaperOrder: (id: string, payload: Record<string, unknown>) =>
    request<{ order: PaperOrder }>(`/api/paper/sessions/${id}/orders`, { method: "POST", body: JSON.stringify(payload) }),
  cancelPaperOrder: (id: string, orderId: string) =>
    request<{ order: PaperOrder; cancelled: boolean }>(`/api/paper/sessions/${id}/orders/${orderId}/cancel`, { method: "POST" }),
  deletePaperSession: (id: string) =>
    request<{ id: string; deleted: boolean }>(`/api/paper/sessions/${id}`, { method: "DELETE" }),
  overfitting: (payload: Record<string, unknown>) => request<OverfittingResult>("/api/research/overfitting", { method: "POST", body: JSON.stringify(payload) }),
  pbo: (payload: Record<string, unknown>) => request<PBOResult>("/api/research/pbo", { method: "POST", body: JSON.stringify(payload) }),
  costSensitivity: (payload: Record<string, unknown>) => request<CostSensitivityResult>("/api/research/cost_sensitivity", { method: "POST", body: JSON.stringify(payload) }),
  monteCarlo: (payload: Record<string, unknown>) => request<MonteCarloResult>("/api/research/monte_carlo", { method: "POST", body: JSON.stringify(payload) }),
  capacity: (payload: Record<string, unknown>) => request<CapacityResult>("/api/research/capacity", { method: "POST", body: JSON.stringify(payload) }),
  factor: (payload: Record<string, unknown>) => request<FactorResult>("/api/research/factor", { method: "POST", body: JSON.stringify(payload) }),
  factorCorrelation: (payload: Record<string, unknown>) => request<FactorCorrelationResult>("/api/research/factor_correlation", { method: "POST", body: JSON.stringify(payload) }),
  sweep: (payload: Record<string, unknown>) => request<SweepResult>("/api/research/sweep", { method: "POST", body: JSON.stringify(payload) }),
  walkForward: (payload: Record<string, unknown>) => request<WalkForwardResult>("/api/research/walk_forward", { method: "POST", body: JSON.stringify(payload) }),
  attribution: (runId: string) => request<AttributionResult>("/api/research/attribution", { method: "POST", body: JSON.stringify({ run_id: runId }) }),
};

export type { SnapshotInfo, JobResult };
