import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PaperSessionDetail, PaperSessionSummary } from "../api/types";
import { api } from "../api/client";
import PaperPage from "./PaperPage";

vi.mock("../api/client", () => ({
  api: {
    paperSessions: vi.fn(), paperSession: vi.fn(), snapshots: vi.fn(), securities: vi.fn(),
    paperAutoStatus: vi.fn(), stepPaper: vi.fn(),
    createPaperSession: vi.fn(), refreshPaper: vi.fn(), submitPaperOrder: vi.fn(), resetPaper: vi.fn(),
  },
  getApiBase: () => "", getToken: () => "",
}));
vi.mock("../components/PaperPortfolioPanel", () => ({ default: () => null }));
vi.mock("../components/Chart", () => ({ default: () => null }));
vi.mock("../lib/notify", () => ({ notify: vi.fn() }));

function session(id: string, name: string, current_date: number): PaperSessionSummary {
  return {
    id, name, current_date, status: "active", snapshot: "snapshot", start_date: 20240102,
    end_date: 20241231, cash: 1000, equity: 1000, starting_cash: 1000,
    position_count: 0, pending_orders: 0, synthetic: true, created_at: "", updated_at: "",
  };
}
const first = session("paper_000000000001", "账户 A", 20240102);
const second = session("paper_000000000002", "账户 B", 20240104);
function detail(summary: PaperSessionSummary): PaperSessionDetail {
  return {
    session: summary, snapshot: {}, account: { cash: 1000, equity: 1000, market_value: 0, pnl: 0, pnl_pct: 0 },
    positions: [], orders: [], trades: [], equity_curve: [], fills: [],
  };
}

describe("paper account selection", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    vi.mocked(api.paperSessions).mockResolvedValue([first, second]);
    vi.mocked(api.snapshots).mockResolvedValue([]);
    vi.mocked(api.securities).mockResolvedValue([]);
    vi.mocked(api.paperAutoStatus).mockImplementation(async (session_id) => ({ session_id, running: false }));
    vi.mocked(api.paperSession).mockImplementation(async (id) => detail(id === first.id ? first : second));
  });
  afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

  it("stops playback on selection change and ignores the previous account's pending step", async () => {
    let finishStep!: (value: PaperSessionDetail) => void;
    vi.mocked(api.stepPaper).mockReturnValue(new Promise((resolve) => { finishStep = resolve; }));
    render(<MemoryRouter><PaperPage /></MemoryRouter>);
    await screen.findByText(/^2024-01-02 \/ 2024-12-31/);
    fireEvent.click(screen.getByRole("button", { name: "自动推进" }));
    await act(async () => { vi.advanceTimersByTime(900); });
    expect(api.stepPaper).toHaveBeenCalledWith(first.id, 1);
    expect(screen.getByRole("button", { name: "重置" })).toBeDisabled();
    await act(async () => { vi.advanceTimersByTime(1800); });
    expect(api.stepPaper).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /^账户 B/ }));
    await screen.findByText(/^2024-01-04 \/ 2024-12-31/);
    await act(async () => { finishStep(detail({ ...first, current_date: 20240103 })); });

    expect(screen.getByText(/^2024-01-04 \/ 2024-12-31/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^账户 B/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "自动推进" })).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(1800); });
    expect(api.stepPaper).toHaveBeenCalledTimes(1);
  });

  it("creates a live account without a historical snapshot and shows quote waiting reasons", async () => {
    const live = { ...first, mode: "live" as const, snapshot: null, name: "实时账户" };
    const current = { ...detail(live), live: { state: "waiting", as_of: null, notice: "行情陈旧，等待有效报价", quotes: [{ code: "600000", timestamp: null, price: 10, reason: "缺少时间戳" }] } };
    vi.mocked(api.paperSessions).mockResolvedValueOnce([]).mockResolvedValue([live]);
    vi.mocked(api.createPaperSession).mockResolvedValue(live);
    vi.mocked(api.paperSession).mockResolvedValue(current);
    vi.mocked(api.refreshPaper).mockResolvedValue(current);
    render(<MemoryRouter><PaperPage /></MemoryRouter>);
    const create = screen.getByRole("button", { name: "创建会话" });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox", { name: "行情模式" }), { target: { value: "live" } });
    expect(create).not.toBeDisabled();
    fireEvent.click(create);
    await waitFor(() => expect(api.createPaperSession).toHaveBeenCalledWith({ mode: "live", snapshot: null, initial_cash: 1000000, name: undefined }));
    await screen.findByRole("button", { name: "刷新实时账户" });
    expect(screen.queryByRole("button", { name: "下一交易日" })).not.toBeInTheDocument();
    expect(await screen.findByText("行情陈旧，等待有效报价")).toBeInTheDocument();
    expect(screen.getByText(/600000.*缺少时间戳/)).toBeInTheDocument();
    expect(screen.getByText("实时模拟不提供公司行为事件流；这里不展示历史调整记录。")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "公司行为调整记录" })).not.toBeInTheDocument();
  });

  it("submits a live virtual order and refreshes the resulting position", async () => {
    const live = { ...first, mode: "live" as const, snapshot: null, name: "实时账户" };
    const current = detail(live);
    const order = { id: "ord_1", date: 20240102, code: "600000", sec_id: "SH.600000", name: "浦发银行", side: "buy" as const, qty: 100, order_type: "market" as const, limit_price: null, status: "pending", filled_qty: 0, fill_price: null, fill_date: null, fees: null, reason: null, created_at: "" };
    const filled = { ...current, positions: [{ sec_id: "SH.600000", code: "600000", name: "浦发银行", board: "MAIN", qty: 100, available: 0, avg_cost: 10.05, last: 10, market_value: 1000, pnl: -5, pnl_pct: -0.005, quote_timestamp: "2026-11-02T10:15:35+08:00" }] };
    vi.mocked(api.paperSessions).mockResolvedValue([live]);
    vi.mocked(api.paperSession).mockResolvedValue(current);
    vi.mocked(api.refreshPaper).mockResolvedValueOnce(current).mockResolvedValue(filled);
    vi.mocked(api.submitPaperOrder).mockResolvedValue({ order });
    render(<MemoryRouter><PaperPage /></MemoryRouter>);
    await screen.findByRole("button", { name: "刷新实时账户" });
    fireEvent.change(screen.getByRole("combobox", { name: "代码" }), { target: { value: "600000" } });
    fireEvent.click(screen.getByRole("button", { name: "提交委托" }));
    await waitFor(() => expect(api.submitPaperOrder).toHaveBeenCalledWith(first.id, { code: "600000", side: "buy", qty: 100, order_type: "market" }));
    await act(async () => { vi.advanceTimersByTime(3000); });
    expect(await screen.findByText("浦发银行")).toBeInTheDocument();
    expect(screen.getByText("2026-11-02T10:15:35+08:00")).toBeInTheDocument();
  });

  it("explains historical cash/share adjustments and canceled orders, then clears them on reset", async () => {
    vi.mocked(api.paperSessions).mockResolvedValue([first]);
    vi.mocked(api.paperSession).mockResolvedValue({ ...detail(first), corporate_events: [{
      date: 20240103, code: "600000", sec_id: "SH.600000", cash: 50, qty_before: 100, qty_after: 200,
      cancelled_order_ids: ["ord_before_split"], reason: "cash and split", model: "pre_tax_ex_date_approximation",
    }] } as PaperSessionDetail);
    vi.mocked(api.resetPaper).mockResolvedValue({ ...detail(first), corporate_events: [] } as PaperSessionDetail);
    render(<MemoryRouter><PaperPage /></MemoryRouter>);
    expect(await screen.findByRole("list", { name: "公司行为调整记录" })).toBeInTheDocument();
    expect(screen.getByText(/现金变化.*50\.00/)).toBeInTheDocument();
    expect(screen.getByText("股数 100 → 200")).toBeInTheDocument();
    fireEvent.click(screen.getByText("已撤销 1 笔相关委托"));
    expect(screen.getByText("ord_before_split")).toBeInTheDocument();
    expect(screen.getByText(/税前.*除权日近似/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重置" }));
    expect(await screen.findByText("暂无公司行为调整")).toBeInTheDocument();
    expect(screen.queryByText("ord_before_split")).not.toBeInTheDocument();
  });
});
