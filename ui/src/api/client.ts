import type { BacktestRequest, BacktestResult, Health, PanelInfo } from "./types";

const API_KEY = "qc_api";
const TOKEN_KEY = "qc_token";

export function getApiBase(): string {
  return localStorage.getItem(API_KEY) || "http://127.0.0.1:8765";
}
export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function configure(base: string, token: string): void {
  localStorage.setItem(API_KEY, base.replace(/\/+$/, ""));
  localStorage.setItem(TOKEN_KEY, token);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  panels: () => request<PanelInfo[]>("/api/panels"),
  runBacktest: (req: BacktestRequest) =>
    request<BacktestResult>("/api/backtest", { method: "POST", body: JSON.stringify(req) }),
  experiments: () => request<Array<Record<string, unknown>>>("/api/experiments"),
};
