import { createElement as h } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { configure, getApiBase, getToken, probeConnection } from "./client";
import SettingsPage from "../pages/SettingsPage";

const health = { status: "ok", version: "2.0.0", engine_backend: "cpp", engine_available: true };
const meta = { version: "2.0.0", engine_backend: "cpp", data_root: "data", synthetic_only: true };
const savedBase = "http://127.0.0.1:8000";
const draftBase = "http://127.0.0.1:9100";
function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

describe("authenticated connection probe", () => {
  beforeEach(() => configure(savedBase, "saved-token"));
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("rejects a healthy public endpoint when protected metadata returns 401", async () => {
    const fetcher = vi.fn(async (url: string) => url.endsWith("/health") ? json(health) : json({ detail: "invalid token" }, 401));
    vi.stubGlobal("fetch", fetcher);
    await expect(probeConnection(draftBase, "wrong-token")).rejects.toMatchObject({ status: 401 });
    expect(fetcher.mock.calls.some(([url]) => url === `${draftBase}/health`)).toBe(true);
    expect(fetcher.mock.calls.some(([url]) => url === `${draftBase}/api/meta`)).toBe(true);
  });

  it("uses the unsaved base and token without changing saved settings, and returns the C++ version", async () => {
    const fetcher = vi.fn(async (url: string) => url.endsWith("/health") ? json(health) : json(meta));
    vi.stubGlobal("fetch", fetcher);
    const saved = vi.spyOn(Storage.prototype, "setItem");
    const result = await probeConnection(` ${draftBase}/// `, " draft-token ");
    expect(result.meta.engine_backend).toBe("cpp");
    expect(result.meta.version).toBe("2.0.0");
    expect(result.health.status).toBe("ok");
    for (const [url, init] of fetcher.mock.calls as unknown as [string, RequestInit][]) {
      expect(url.startsWith(`${draftBase}/`)).toBe(true);
      expect(new Headers(init.headers).get("Authorization")).toBe("Bearer draft-token");
    }
    expect(saved).not.toHaveBeenCalled();
    expect(getApiBase()).toBe(savedBase);
    expect(getToken()).toBe("saved-token");
    fetcher.mockClear();
    await probeConnection(draftBase, "");
    for (const [, init] of fetcher.mock.calls as unknown as [string, RequestInit][]) {
      expect(new Headers(init.headers).has("Authorization")).toBe(false);
    }
    expect(getToken()).toBe("saved-token");
  });

  it("shows authentication failure for saved settings and tests the actual form draft", async () => {
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/health")) return json(health);
      if (url.endsWith("/api/meta")) {
        return url.startsWith(draftBase) && new Headers(init?.headers).get("Authorization") === "Bearer draft-token"
          ? json(meta) : json({ detail: "invalid token" }, 401);
      }
      if (url.endsWith("/api/live/status")) return json({ enabled: false });
      return json({ snapshots: [], providers: [] });
    });
    vi.stubGlobal("fetch", fetcher);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(h(QueryClientProvider, { client }, h(MemoryRouter, null, h(SettingsPage))));
    expect(await screen.findByText("验证失败")).toBeInTheDocument();
    expect(screen.queryByText("已连接")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("API 地址"), { target: { value: draftBase } });
    fireEvent.change(screen.getByLabelText("Bearer Token"), { target: { value: "draft-token" } });
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await waitFor(() => expect(screen.getByText(/^已连接：cpp · v2.0.0/)).toBeInTheDocument());
    expect(getApiBase()).toBe(savedBase);
    expect(getToken()).toBe("saved-token");
  });
});
