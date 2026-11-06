import { describe, expect, it } from "vitest";
import { drawdowns, monthlyReturns } from "./backtestAnalysis";

describe("recorded equity analytics", () => {
  it("includes month-boundary moves and reconciles compounded returns", () => {
    const months = monthlyReturns([20240130, 20240131, 20240201, 20240229, 20240301], [99, 110, 99, 121, 108.9], 100);
    expect(months.map((item) => item.month)).toEqual(["2024-01", "2024-02", "2024-03"]);
    expect(months[0].value).toBeCloseTo(0.1);
    expect(months[1].value).toBeCloseTo(0.1);
    expect(months[2].value).toBeCloseTo(-0.1);
    expect(months.reduce((capital, item) => capital * (1 + item.value), 100)).toBeCloseTo(108.9);
  });

  it("records losses from the initial capital and keeps historical peaks", () => {
    expect(drawdowns([90, 80, 110, 99], 100)).toEqual(expect.arrayContaining([
      expect.closeTo(-0.1), expect.closeTo(-0.2), 0,
    ]));
    expect(drawdowns([90, 80, 110, 99], 100).at(-1)).toBeCloseTo(-0.1);
    expect(drawdowns([], 100)).toEqual([]);
  });
});
