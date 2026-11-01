import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function resolveThemeColors(value: unknown): unknown {
  if (typeof value === "string") {
    return value.replace(/var\(--([a-z0-9-]+)\)/gi, (_, name: string) => cssVar(`--${name}`) || "#888888");
  }
  if (Array.isArray(value)) return value.map(resolveThemeColors);
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) output[key] = resolveThemeColors(item);
    return output;
  }
  return value;
}

export default function Chart({ option, height = 320, className }: { option: EChartsOption; height?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    let chart: echarts.ECharts | null = null;
    const build = () => {
      chart?.dispose();
      const dark = document.documentElement.dataset.theme === "dark";
      chart = echarts.init(ref.current, dark ? "dark" : undefined, { renderer: "canvas" });
      chart.setOption({ backgroundColor: "transparent", ...(resolveThemeColors(option) as EChartsOption) });
    };
    build();
    const resize = new ResizeObserver(() => chart?.resize());
    resize.observe(ref.current);
    const themeObserver = new MutationObserver(build);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-color-mode"] });
    return () => { resize.disconnect(); themeObserver.disconnect(); chart?.dispose(); };
  }, [option]);
  return <div ref={ref} className={className} style={{ width: "100%", height }} role="img" aria-label="chart" />;
}
