import { describe, expect, it } from "vitest";
import type { CompareResult } from "../api/types";
import { comparisonSeries, metricDelta } from "./experimentComparison";

describe("experiment comparison", () => {
  it("plots normalized equity across different capitals and preserves initial-day losses", () => {
    const result = {
      equity: [
        { run_id: "a", label: "A", dates: [20240102, 20240103], equity: [990, 1100], normalized_equity: [0.99, 1.1], drawdown: [-0.01, 0] },
        { run_id: "b", label: "B", dates: [20240102, 20240103], equity: [9900, 11000], normalized_equity: [0.99, 1.1], drawdown: [-0.01, 0] },
      ],
    } as CompareResult;
    const series = comparisonSeries(result, "equity", ["blue", "orange"]);
    expect(series[0].data).toEqual(series[1].data);
    expect(series[0].data[0]).toEqual({ time: 20240102, value: 0.99 });
    expect(comparisonSeries(result, "drawdown", ["blue"])[0].data[0]).toEqual({ time: 20240102, value: -1 });
  });

  it("does not substitute raw yuan when initial capital is unrecorded", () => {
    const result = { equity: [{ run_id: "legacy", label: "旧记录", dates: [20240102], equity: [1000], normalized_equity: null, drawdown: [0] }] } as CompareResult;
    expect(comparisonSeries(result, "equity", ["blue"])).toEqual([]);
  });

  it("expresses return deltas in percentage points and leaves missing metrics unscored", () => {
    expect(metricDelta(0.12, 0.08, "ratio")).toBe("+4.00 个百分点");
    expect(metricDelta(0.8, 1.2, "number")).toBe("-0.40");
    expect(metricDelta(undefined, 0.08, "ratio")).toBe("—");
  });
});
