import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { SecurityRow } from "../api/types";
import { useWorkspace } from "../store/workspace";
import MarketPage from "./MarketPage";

vi.mock("../api/client", () => ({ api: {
  securities: vi.fn(), overview: vi.fn(), liveStatus: vi.fn(), liveIndices: vi.fn(), watchlist: vi.fn(),
  bars: vi.fn(), securityProfile: vi.fn(), financials: vi.fn(), dataIntegrity: vi.fn(),
} }));
vi.mock("../components/KLineChart", () => ({ default: () => null }));
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
});
