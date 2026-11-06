import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PaperSessionDetail, PaperSessionSummary } from "../api/types";
import { api } from "../api/client";
import PaperPage from "./PaperPage";

vi.mock("../api/client", () => ({
  api: {
    paperSessions: vi.fn(), paperSession: vi.fn(), snapshots: vi.fn(), securities: vi.fn(),
    paperAutoStatus: vi.fn(), stepPaper: vi.fn(),
  },
  getApiBase: () => "", getToken: () => "",
}));
vi.mock("../components/PaperPortfolioPanel", () => ({ default: () => null }));
vi.mock("../components/Chart", () => ({ default: () => null }));

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
});
