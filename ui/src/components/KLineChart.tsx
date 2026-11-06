import { useEffect, useRef } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, createChart,
  type CandlestickData, type HistogramData, type IChartApi, type ISeriesApi, type LineData, type Time,
} from "lightweight-charts";
import type { Bars } from "../api/types";
import { useChartPalette, type ChartPalette } from "../theme";
import { num } from "../lib/format";
import { chartToken } from "../lib/tokens";

interface Props {
  bars: Bars;
  palette?: ChartPalette;
  height?: number;
  showMA5?: boolean;
  showMA20?: boolean;
  showVolume?: boolean;
}

/** Local-only TradingView Lightweight Charts wrapper; no remote assets. */
export default function KLineChart({ bars, palette: paletteProp, height = 430, showMA5 = true, showMA20 = true, showVolume = true }: Props) {
  const hookPalette = useChartPalette();
  const palette = paletteProp ?? hookPalette;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ma5Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const fittedCode = useRef<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      width: Math.max(container.clientWidth, 320),
      height: Math.max(container.clientHeight, 240),
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: palette.text,
        fontFamily: "PingFang SC, Microsoft YaHei, -apple-system, sans-serif",
        attributionLogo: false,
      },
      grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: palette.grid },
      timeScale: { borderColor: palette.grid, timeVisible: false, secondsVisible: false, rightOffset: 3 },
      localization: { priceFormatter: (price: number) => price.toFixed(2) },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: palette.up, downColor: palette.down, borderUpColor: palette.up, borderDownColor: palette.down,
      wickUpColor: palette.up, wickDownColor: palette.down,
    });
    const ma5 = chart.addSeries(LineSeries, { color: chartToken("--warn", "#eab308"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    const ma20 = chart.addSeries(LineSeries, { color: palette.accent, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume", lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
    chartRef.current = chart;
    candleRef.current = candle;
    ma5Ref.current = ma5;
    ma20Ref.current = ma20;
    volumeRef.current = volume;
    const resize = new ResizeObserver(() => {
      chart.applyOptions({ width: Math.max(container.clientWidth, 320), height: Math.max(container.clientHeight, 240) });
    });
    resize.observe(container);
    return () => {
      resize.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      ma5Ref.current = null;
      ma20Ref.current = null;
      volumeRef.current = null;
    };
    // The chart is independent from data after creation; palette updates are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const candle = candleRef.current;
    const ma5 = ma5Ref.current;
    const ma20 = ma20Ref.current;
    if (!candle || !ma5 || !ma20) return;
    const time = (index: number) => bars.dates[index] as Time;
    const candles: CandlestickData<Time>[] = bars.dates.map((_, index) => ({
      time: time(index), open: bars.open[index], high: bars.high[index], low: bars.low[index], close: bars.close[index],
    }));
    const line = (values: Array<number | null>): LineData<Time>[] => values.flatMap((value, index) => (
      value == null || !Number.isFinite(value) ? [] : [{ time: time(index), value }]
    ));
    candle.setData(candles);
    ma5.setData(line(bars.ma5));
    ma20.setData(line(bars.ma20));
    if (fittedCode.current !== bars.code) {
      chartRef.current?.timeScale().fitContent();
      fittedCode.current = bars.code;
    }
  }, [bars]);

  useEffect(() => {
    candleRef.current?.applyOptions({ upColor: palette.up, downColor: palette.down, borderUpColor: palette.up, borderDownColor: palette.down, wickUpColor: palette.up, wickDownColor: palette.down });
    ma20Ref.current?.applyOptions({ color: palette.accent });
    chartRef.current?.applyOptions({
      layout: { textColor: palette.text },
      grid: { vertLines: { color: palette.grid }, horzLines: { color: palette.grid } },
      rightPriceScale: { borderColor: palette.grid },
      timeScale: { borderColor: palette.grid },
    });
  }, [palette]);

  useEffect(() => {
    ma5Ref.current?.applyOptions({ visible: showMA5 });
    ma20Ref.current?.applyOptions({ visible: showMA20 });
    volumeRef.current?.applyOptions({ visible: showVolume });
  }, [showMA5, showMA20, showVolume]);

  useEffect(() => {
    const volume = volumeRef.current;
    if (!volume) return;
    const data: HistogramData<Time>[] = bars.dates.map((date, index) => ({
      time: date as Time,
      value: bars.volume[index] ?? 0,
      color: bars.close[index] >= bars.open[index] ? `${palette.up}88` : `${palette.down}88`,
    }));
    volume.setData(data);
  }, [bars, palette]);

  const last = bars.close.at(-1);
  const previous = bars.close.at(-2);
  return (
    <div className="kline-wrap" style={{ height }}>
      <div className="kline-legend">
        <strong>{bars.code} {bars.name}</strong>
        <span className={last != null && previous != null && last >= previous ? "up" : "down"}>{num(last)}</span>
        <span className="muted">MA5 {showMA5 ? num(bars.ma5.at(-1)) : "off"}</span>
        <span className="muted">MA20 {showMA20 ? num(bars.ma20.at(-1)) : "off"}</span>
      </div>
      <div ref={containerRef} className="kline-canvas" aria-label={`${bars.code} K线`} />
    </div>
  );
}
