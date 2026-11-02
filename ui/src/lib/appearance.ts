/** Theme / density / up-down colour mode, shared by App and Settings. */

export type ThemeMode = "light" | "dark";
export type DensityMode = "comfortable" | "compact" | "spacious";
export type ColorMode = "red-up" | "green-up" | "color-blind";

export interface Appearance {
  theme: ThemeMode;
  density: DensityMode;
  colorMode: ColorMode;
}

const KEYS = { theme: "qc_theme", density: "qc_density", colorMode: "qc_color_mode" } as const;

function read(key: string, fallback: string): string {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

export function readAppearance(): Appearance {
  return {
    theme: read(KEYS.theme, "light") === "dark" ? "dark" : "light",
    density: (read(KEYS.density, "comfortable") as DensityMode),
    colorMode: (read(KEYS.colorMode, "red-up") as ColorMode),
  };
}

/** Apply appearance to <html>; optionally persist a new value first. */
export function applyAppearance(next?: Partial<Appearance>): Appearance {
  const current = readAppearance();
  const merged: Appearance = { ...current, ...next };
  if (next) {
    try {
      if (next.theme) localStorage.setItem(KEYS.theme, merged.theme);
      if (next.density) localStorage.setItem(KEYS.density, merged.density);
      if (next.colorMode) localStorage.setItem(KEYS.colorMode, merged.colorMode);
    } catch { /* storage may be unavailable; still apply for this session */ }
  }
  const root = document.documentElement;
  root.dataset.theme = merged.theme;
  root.dataset.density = merged.density;
  root.dataset.colorMode = merged.colorMode;
  return merged;
}

export function toggleTheme(): Appearance {
  const current = readAppearance();
  const next = applyAppearance({ theme: current.theme === "dark" ? "light" : "dark" });
  window.dispatchEvent(new Event("qc-settings"));
  return next;
}

/** Listen for settings changes from the Settings page or another tab. */
export function subscribeAppearance(onChange: (next: Appearance) => void): () => void {
  const local = () => onChange(applyAppearance());
  const storage = (event: StorageEvent) => {
    if (event.key && Object.values(KEYS).includes(event.key as (typeof KEYS)[keyof typeof KEYS])) onChange(applyAppearance());
  };
  window.addEventListener("qc-settings", local);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener("qc-settings", local);
    window.removeEventListener("storage", storage);
  };
}
