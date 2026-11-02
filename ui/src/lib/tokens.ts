/** Resolve CSS design tokens for canvas chart libraries (they cannot read var()). */

export function cssToken(name: string, fallback = ""): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Chart colour from a token, with a literal fallback for non-DOM environments. */
export function chartToken(name: string, fallback: string): string {
  return cssToken(name, fallback);
}
