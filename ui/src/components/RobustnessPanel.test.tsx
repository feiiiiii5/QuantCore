import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CostSensitivityResult, Experiment } from "../api/types";
import RobustnessPanel from "./RobustnessPanel";

afterEach(() => { vi.unstubAllGlobals(); });

describe("cost sensitivity scenarios", () => {
  it("renders fractional and single-scenario API results without treating multipliers as dates", async () => {
    const fetchResult = vi.fn<(...args: Parameters<typeof fetch>) => ReturnType<typeof fetch>>();
    vi.stubGlobal("fetch", fetchResult);
    const experiment: Experiment = { run_id: "run-a", kind: "backtest", created_at: "2026-11-06", status: "completed", strategy_name: "成本情景", template: "momentum", snapshot_id: null, content_hash: "fixture", metrics: null, tags: [], note: "", synthetic: true };
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><RobustnessPanel experiments={[experiment]} initialRunId="run-a" /></QueryClientProvider>);
    const variants = [
      { multipliers: "0, 0.5, 1, 2, 3", points: [
        { multiplier: 0, total_return: 0.12, annualized_return: 0.06, sharpe: 1.1, max_drawdown: 0.04, total_fees: 0 },
        { multiplier: 0.5, total_return: 0.1023, annualized_return: 0.052, sharpe: 0.95, max_drawdown: 0.05, total_fees: 123400 },
        { multiplier: 1, total_return: 0.08, annualized_return: 0.04, sharpe: 0.8, max_drawdown: 0.06, total_fees: 246800 },
        { multiplier: 2, total_return: 0.04, annualized_return: 0.02, sharpe: 0.3, max_drawdown: 0.08, total_fees: 493600 },
        { multiplier: 3, total_return: -0.01, annualized_return: -0.005, sharpe: -0.2, max_drawdown: 0.1, total_fees: 740400 },
      ], expected: [
        ["0×", "12.00%", "6.00%", "1.10", "4.00%", "¥0.00"],
        ["0.5×", "10.23%", "5.20%", "0.95", "5.00%", "¥12.34"],
        ["1×", "8.00%", "4.00%", "0.80", "6.00%", "¥24.68"],
        ["2×", "4.00%", "2.00%", "0.30", "8.00%", "¥49.36"],
        ["3×", "-1.00%", "-0.50%", "-0.20", "10.00%", "¥74.04"],
      ] },
      { multipliers: "0.25, 0.5, 1.5", points: [
        { multiplier: 0.25, total_return: 0.0257, annualized_return: 0.02, sharpe: 0.2, max_drawdown: 0.01, total_fees: 1234 },
        { multiplier: 0.5, total_return: 0, annualized_return: 0, sharpe: 0, max_drawdown: 0.02, total_fees: 25000 },
        { multiplier: 1.5, total_return: -0.03, annualized_return: -0.02, sharpe: -0.4, max_drawdown: 0.05, total_fees: 75000 },
      ], expected: [
        ["0.25×", "2.57%", "2.00%", "0.20", "1.00%", "¥0.12"],
        ["0.5×", "0.00%", "0.00%", "0.00", "2.00%", "¥2.50"],
        ["1.5×", "-3.00%", "-2.00%", "-0.40", "5.00%", "¥7.50"],
      ] },
      { multipliers: "0.125", points: [
        { multiplier: 0.125, total_return: -0.075, annualized_return: -0.05, sharpe: -0.6, max_drawdown: 0.12, total_fees: 37500 },
      ], expected: [["0.125×", "-7.50%", "-5.00%", "-0.60", "12.00%", "¥3.75"]] },
    ];

    for (const variant of variants) {
      const response: CostSensitivityResult = { run_id: "run-a", breakeven_multiplier: null, points: variant.points };
      fetchResult.mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 200, headers: { "Content-Type": "application/json" } }));
      fireEvent.change(screen.getByLabelText("成本倍数"), { target: { value: variant.multipliers } });
      fireEvent.click(screen.getByRole("button", { name: "成本敏感性" }));
      await waitFor(() => {
        const table = screen.getByRole("table", { name: "成本情景指标" });
        const rows = within(table).getAllByRole("row").slice(1);
        expect(rows.map((row) => [within(row).getByRole("rowheader"), ...within(row).getAllByRole("cell")].map((cell) => cell.textContent))).toEqual(variant.expected);
      });
      const bars = screen.getByRole("figure", { name: "费用倍数与总收益" });
      expect(within(bars).getAllByRole("listitem")).toHaveLength(variant.points.length);
      for (const point of variant.points) expect(within(bars).getByText(`${point.multiplier}×`, { exact: true })).toBeVisible();
      const [url, request] = fetchResult.mock.calls.at(-1)!;
      expect(url).toBe("/api/research/cost_sensitivity");
      expect(JSON.parse(request?.body as string)).toEqual({ run_id: "run-a", multipliers: variant.points.map((point) => point.multiplier) });
    }
    expect(fetchResult).toHaveBeenCalledTimes(3);
  });
});
