import type { CompareResult } from "../api/types";
import type { ChartSeries } from "../components/Chart";

export type ComparisonView = "equity" | "drawdown";

export function comparisonSeries(result: CompareResult, view: ComparisonView, colors: string[]): ChartSeries[] {
  return result.equity.flatMap((run, index) => {
    const values = view === "equity" ? run.normalized_equity : run.drawdown;
    if (!values?.length) return [];
    return [{
      kind: "line" as const,
      title: `${index + 1}. ${run.label}`,
      color: colors[index % colors.length],
      data: run.dates.map((date, point) => ({ time: date, value: view === "drawdown" ? values[point] * 100 : values[point] })),
    }];
  });
}

export function metricDelta(value: number | undefined, baseline: number | undefined, unit: "ratio" | "number"): string {
  if (value == null || baseline == null || !Number.isFinite(value) || !Number.isFinite(baseline)) return "—";
  const delta = value - baseline;
  const scaled = unit === "ratio" ? delta * 100 : delta;
  return `${scaled >= 0 ? "+" : ""}${scaled.toFixed(2)}${unit === "ratio" ? " 个百分点" : ""}`;
}

export function comparisonValue(value: unknown): string {
  if (value == null) return "未记录";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}
