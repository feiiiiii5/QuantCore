import { describe, expect, it } from "vitest";
import type { Bars, LiveQuote, SecurityProfile } from "../api/types";
import { marketReadings, withLiveCandle } from "./live";

const bars = {
  code: "600000", name: "浦发银行", board: "MAIN", synthetic: false,
  dates: ["2026-11-05", "2026-11-06"], open: [10, 11], high: [11, 12], low: [9, 10], close: [10.5, 11.5],
  volume: [100, 200], amount: [1000, 2200], turnover: [1, 2], ma5: [null, null], ma20: [null, null],
  limit_up: [], limit_down: [], suspended: [],
} as Bars;
const quote = {
  code: "600000", name: "浦发银行", timestamp: "2026-11-06T10:30:00+08:00", open: 11, high: 12.5, low: 10,
  price: 12, volume: 300, amount: 3300, turnover_pct: 3,
} as LiveQuote;

describe("source-timestamped daily candle updates", () => {
  it("updates only the selected security's current day without mutating history", () => {
    const next = withLiveCandle(bars, quote);
    expect(next.dates).toEqual(bars.dates);
    expect(next.close).toEqual([10.5, 12]);
    expect(next.volume).toEqual([100, 300]);
    expect(next.amount).toEqual([1000, 3300]);
    expect(bars.close).toEqual([10.5, 11.5]);
    expect(withLiveCandle(bars, { ...quote, code: "000001" })).toBe(bars);
    expect(withLiveCandle(bars, { ...quote, timestamp: null })).toBe(bars);
    expect(withLiveCandle(bars, { ...quote, timestamp: "2026-11-05T10:30:00+08:00" })).toBe(bars);
    expect(withLiveCandle({ ...bars, synthetic: true }, quote).close).toEqual(bars.close);
  });

  it("appends a new source day and keeps indicator arrays aligned", () => {
    const next = withLiveCandle(bars, { ...quote, timestamp: "2026-11-09T01:30:00Z" });
    expect(next.dates).toEqual([...bars.dates, "2026-11-09"]);
    expect(next.close).toEqual([...bars.close, 12]);
    for (const field of ["open", "high", "low", "volume", "amount", "turnover", "ma5", "ma20"] as const) {
      expect(next[field]).toHaveLength(next.dates.length);
    }
  });

  it("does not mix recent public candles with an old local profile's change or date", () => {
    const readings = marketReadings({ bars, profile: { quote: { date: 20241231, change_pct: -9 } } as SecurityProfile });
    expect(readings.changePct).toBeCloseTo((11.5 / 10.5 - 1) * 100);
    expect(readings.updatedAt).toBe("2026-11-06");
  });
});
