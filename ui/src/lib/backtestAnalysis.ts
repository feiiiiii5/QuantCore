import { monthKey } from "./format";

/** Include the initial capital in the peak, then update it in one pass. */
export function drawdowns(equity: number[], initialCash?: number): number[] {
  let peak = initialCash ?? equity[0] ?? 0;
  return equity.map((value) => {
    peak = Math.max(peak, value);
    return peak > 0 ? value / peak - 1 : 0;
  });
}

/** A month starts at the previous month's close, including the first trading day's move. */
export function monthlyReturns(dates: number[], equity: number[], initialCash?: number) {
  const months = new Map<string, { base: number; last: number }>();
  let previous = initialCash ?? equity[0];
  dates.forEach((date, index) => {
    const month = monthKey(date);
    const bucket = months.get(month);
    if (bucket) bucket.last = equity[index];
    else months.set(month, { base: previous, last: equity[index] });
    previous = equity[index];
  });
  return [...months].map(([month, { base, last }]) => ({
    month, value: base > 0 ? last / base - 1 : 0,
  }));
}
