import { useEffect, useMemo, useRef } from "react";
import {
  AreaSeries,
  BaselineSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { useChartPalette } from "../theme";

/** Declarative wrapper over TradingView Lightweight Charts (mature OSS, local-only).
 *
 * Pages describe series instead of canvas options:
 *
 *   <Chart series={[{ kind: "area", data: equity.map((p) => ({ time: p.date, value: p.value })), title: "净值" }]} />
 *
 * `time` accepts YYYYMMDD integers, epoch seconds or ISO date strings, so pages can pass
 * API dates straight through.
 */

export type ChartSeriesKind = "line" | "area" | "histogram" | "candlestick" | "baseline";

export interface ChartPoint {
  time: number | string;
  value: number;
  color?: string;
}

export interface ChartCandle {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartSeries {
  kind: ChartSeriesKind;
  data: Array<ChartPoint | ChartCandle>;
  title?: string;
  color?: string;
  topColor?: string;
  bottomColor?: string;
  lineWidth?: 1 | 2 | 3 | 4;
  pane?: number;
  priceFormat?: "price" | "percent" | "volume";
  lastValueVisible?: boolean;
  priceLineVisible?: boolean;
}

export interface ChartProps {
  series: ChartSeries[];
  height?: number;
  className?: string;
  legend?: boolean;
  ariaLabel?: string;
  valueFormatter?: (value: number) => string;
  timeVisible?: boolean;
}

const DATE_INT_MIN = 18991231;
const DATE_INT_MAX = 21001231;

function toTime(value: number | string): Time {
  if (typeof value === "string") {
    if (value.includes("T") || value.includes("-")) return value as Time;
    if (value.length === 8) {
      return (value.slice(0, 4) + "-" + value.slice(4, 6) + "-" + value.slice(6)) as Time;
    }
    return value as Time;
  }
  if (!Number.isFinite(value)) return 0 as Time;
  if (value >= DATE_INT_MIN && value <= DATE_INT_MAX) {
    const year = Math.floor(value / 10000);
    const month = Math.floor(value / 100) % 100;
    const day = value % 100;
    return (Date.UTC(year, month - 1, day) / 1000) as Time;
  }
  if (value > 4_000_000_000) return Math.floor(value / 1000) as Time;
  return Math.floor(value) as Time;
}

function withAlpha(color: string, alpha: number): string {
  const hex = color.trim();
  if (hex.startsWith("#")) {
    const raw = hex.slice(1);
    const full = raw.length === 3 ? raw.split("").map((part) => part + part).join("") : raw;
    if (full.length === 6) {
      const r = parseInt(full.slice(0, 2), 16);
      const g = parseInt(full.slice(2, 4), 16);
      const b = parseInt(full.slice(4, 6), 16);
      return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
    }
  }
  return color;
}

export default function Chart({
  series,
  height = 320,
  className,
  legend = true,
  ariaLabel = "chart",
  valueFormatter,
  timeVisible = false,
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const palette = useChartPalette();
  const signature = useMemo(() => JSON.stringify(series), [series]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart: IChartApi = createChart(container, {
      width: Math.max(container.clientWidth, 240),
      height: Math.max(height - (legend && series.some((item) => item.title) ? 26 : 0), 160),
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: palette.text,
        fontFamily:
          "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Microsoft YaHei, sans-serif",
        attributionLogo: false,
      },
      grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: palette.grid, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: palette.grid, timeVisible, secondsVisible: false, rightOffset: 2 },
      localization: valueFormatter ? { priceFormatter: valueFormatter } : undefined,
    });

    for (const item of series) {
      const common = {
        title: item.title,
        priceLineVisible: item.priceLineVisible ?? false,
        lastValueVisible: item.lastValueVisible ?? false,
      };
      if (item.kind === "candlestick") {
        const api = chart.addSeries(
          CandlestickSeries,
          {
            ...common,
            upColor: palette.up,
            downColor: palette.down,
            borderUpColor: palette.up,
            borderDownColor: palette.down,
            wickUpColor: palette.up,
            wickDownColor: palette.down,
          },
          item.pane,
        );
        api.setData(
          (item.data as ChartCandle[]).map((point) => ({
            time: toTime(point.time),
            open: point.open,
            high: point.high,
            low: point.low,
            close: point.close,
          })),
        );
      } else if (item.kind === "histogram") {
        const api = chart.addSeries(
          HistogramSeries,
          {
            ...common,
            color: item.color ?? palette.accent,
            priceFormat: { type: item.priceFormat === "volume" ? "volume" : "price" },
          },
          item.pane,
        );
        api.setData(
          (item.data as ChartPoint[]).map((point) => ({
            time: toTime(point.time),
            value: point.value,
            color: point.color,
          })),
        );
      } else if (item.kind === "area") {
        const lineColor = item.color ?? palette.accent;
        const api = chart.addSeries(
          AreaSeries,
          {
            ...common,
            lineColor,
            topColor: item.topColor ?? withAlpha(lineColor, 0.24),
            bottomColor: item.bottomColor ?? withAlpha(lineColor, 0.02),
            lineWidth: item.lineWidth ?? 2,
          },
          item.pane,
        );
        api.setData(
          (item.data as ChartPoint[]).map((point) => ({
            time: toTime(point.time),
            value: point.value,
          })),
        );
      } else if (item.kind === "baseline") {
        const api = chart.addSeries(
          BaselineSeries,
          {
            ...common,
            baseValue: { type: "price", price: 0 },
            topLineColor: item.color ?? palette.up,
            topFillColor1: withAlpha(item.color ?? palette.up, 0.18),
            topFillColor2: withAlpha(item.color ?? palette.up, 0.02),
            bottomLineColor: palette.down,
            bottomFillColor1: withAlpha(palette.down, 0.02),
            bottomFillColor2: withAlpha(palette.down, 0.18),
            lineWidth: item.lineWidth ?? 2,
          },
          item.pane,
        );
        api.setData(
          (item.data as ChartPoint[]).map((point) => ({
            time: toTime(point.time),
            value: point.value,
          })),
        );
      } else {
        const api = chart.addSeries(
          LineSeries,
          { ...common, color: item.color ?? palette.accent, lineWidth: item.lineWidth ?? 2 },
          item.pane,
        );
        api.setData(
          (item.data as ChartPoint[]).map((point) => ({
            time: toTime(point.time),
            value: point.value,
          })),
        );
      }
    }
    chart.timeScale().fitContent();
    // Keep the series fitted after container width changes (sidebar collapse, windows, fonts).
    let frame = 0;
    const resize = new ResizeObserver(() => {
      chart.applyOptions({ width: Math.max(container.clientWidth, 240) });
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => chart.timeScale().fitContent());
    });
    resize.observe(container);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      resize.disconnect();
      chart.remove();
    };
    // signature captures the series content; palette/height changes rebuild the chart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, height, palette, valueFormatter, timeVisible, legend]);

  const titled = series.filter((item) => item.title);
  const showLegend = legend && titled.length > 0;
  return (
    <div className={className ? "chart-root " + className : "chart-root"} style={{ height }}>
      {showLegend ? (
        <div className="chart-legend" aria-hidden="true">
          {titled.map((item, index) => (
            <span className="chart-legend-item" key={(item.title ?? "series") + index}>
              <i style={{ background: item.color ?? "var(--accent)" }} />
              {item.title}
            </span>
          ))}
        </div>
      ) : null}
      <div
        ref={containerRef}
        className="chart-canvas"
        style={{ height: showLegend ? Math.max(height - 30, 120) : height }}
        role="img"
        aria-label={ariaLabel}
      />
    </div>
  );
}
