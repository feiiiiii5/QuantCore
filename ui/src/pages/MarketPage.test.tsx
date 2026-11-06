import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { SecurityRow } from "../api/types";
import { useWorkspace } from "../store/workspace";
import MarketPage from "./MarketPage";

vi.mock("../api/client", () => ({ api: {
  securities: vi.fn(), overview: vi.fn(), liveStatus: vi.fn(), liveIndices: vi.fn(), liveQuotes: vi.fn(), liveBars: vi.fn(), watchlist: vi.fn(),
  bars: vi.fn(), securityProfile: vi.fn(), financials: vi.fn(), dataIntegrity: vi.fn(),
} }));
vi.mock("../components/KLineChart", () => ({ default: () => null }));
vi.mock("../lib/liveStream", () => ({ subscribeLiveQuotes: () => () => undefined }));
vi.mock("../components/VirtualTable", () => ({
  default: ({ data }: { data: SecurityRow[] }) => <div>{data.map((row) => <span key={row.sec_id}>{row.name}</span>)}</div>,
}));

const row = { sec_id: "SH.600999", code: "600999", name: "第1001只证券", industry: "银行", board: "MAIN" } as SecurityRow;

describe("market whole-snapshot search and watchlist", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspace.setState({ marketCode: "", marketQuery: "" });
    vi.mocked(api.overview).mockResolvedValue({
      snapshot: { id: "synthetic", synthetic: true }, indices: [], sectors: [],
      breadth: { up: 0, down: 0, flat: 0, limit_up: 0, limit_down: 0, suspended: 0 },
    } as never);
    vi.mocked(api.liveStatus).mockResolvedValue({ enabled: false } as never);
    vi.mocked(api.watchlist).mockResolvedValue({ codes: [row.code] } as never);
    vi.mocked(api.bars).mockResolvedValue(null as never);
    vi.mocked(api.securityProfile).mockResolvedValue(null as never);
    vi.mocked(api.financials).mockResolvedValue(null as never);
    vi.mocked(api.dataIntegrity).mockResolvedValue(null as never);
    vi.mocked(api.securities).mockImplementation(async (query, _limit, codes) => query === row.code || codes?.includes(row.code) ? [row] : []);
  });

  it("finds and shows a watched security outside the first 1000 rows", async () => {
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><MarketPage /></MemoryRouter>
    </QueryClientProvider>);
    fireEvent.change(await screen.findByRole("textbox", { name: "搜索代码 / 名称 / 行业" }), { target: { value: row.code } });
    expect(await screen.findByText(row.name)).toBeInTheDocument();
    await waitFor(() => expect(api.securities).toHaveBeenCalledWith(row.code, 1000, undefined));

    fireEvent.change(screen.getByRole("textbox", { name: "搜索代码 / 名称 / 行业" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("radio", { name: "我的自选 1" }));
    await waitFor(() => expect(api.securities).toHaveBeenCalledWith("", 1000, [row.code]));
    expect(await screen.findByText(row.name)).toBeInTheDocument();
  });

  it("opens a public daily chart by code even when the security is absent from the local snapshot", async () => {
    vi.mocked(api.securities).mockResolvedValue([]);
    vi.mocked(api.liveStatus).mockResolvedValue({ enabled: true, state: "closed", market: { phase: "closed", last_trade_date: 20261106 } } as never);
    vi.mocked(api.liveIndices).mockResolvedValue({ quotes: [] } as never);
    vi.mocked(api.liveQuotes).mockResolvedValue({ quotes: [], stale: true } as never);
    vi.mocked(api.liveBars).mockResolvedValue({
      code: "603999", name: "非本地证券", dates: ["2026-11-06"], close: [10], open: [10], high: [11], low: [9],
      volume: [100], amount: [1000], turnover: [null], ma5: [null], ma20: [null], limit_up: [], limit_down: [], suspended: [],
      synthetic: false, source: "eastmoney", note: "公开日线 · 不复权",
    } as never);
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
      <MemoryRouter><MarketPage /></MemoryRouter>
    </QueryClientProvider>);
    const input = await screen.findByRole("textbox", { name: "搜索代码 / 名称 / 行业" });
    fireEvent.change(input, { target: { value: "603999" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("603999 非本地证券")).toBeInTheDocument();
    await waitFor(() => expect(api.liveBars).toHaveBeenCalledWith("603999"));
    expect(screen.getByText(/公开日线 · 不复权 · eastmoney/)).toBeInTheDocument();
  });
});
