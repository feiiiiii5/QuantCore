import { useEffect, useState } from "react";

export interface ChartPalette {
  up: string;
  down: string;
  text: string;
  grid: string;
  accent: string;
}

function readPalette(): ChartPalette {
  if (typeof window === "undefined") {
    return { up: "#e5484d", down: "#12a150", text: "#1a1d21", grid: "rgba(148,163,184,.18)", accent: "#2563eb" };
  }
  const style = getComputedStyle(document.documentElement);
  const value = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    up: value("--up", "#e5484d"),
    down: value("--down", "#12a150"),
    text: value("--text", "#1a1d21"),
    grid: value("--separator", value("--line", "#e5e7eb")),
    accent: value("--accent", "#2563eb"),
  };
}

/** Chart palette derived from CSS tokens; updates on theme/color-mode changes. */
export function useChartPalette(): ChartPalette {
  const [palette, setPalette] = useState<ChartPalette>(readPalette);
  useEffect(() => {
    const refresh = () => setPalette(readPalette());
    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-color-mode", "data-density"],
    });
    window.addEventListener("qc-settings", refresh);
    return () => {
      observer.disconnect();
      window.removeEventListener("qc-settings", refresh);
    };
  }, []);
  return palette;
}
