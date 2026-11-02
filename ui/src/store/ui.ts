import { create } from "zustand";

const BEGINNER_KEY = "qc_beginner";

function readBeginner(): boolean {
  try {
    const raw = localStorage.getItem(BEGINNER_KEY);
    if (raw == null) return true;
    return raw !== "0" && raw !== "false";
  } catch {
    return true;
  }
}

export interface UIState {
  /** Beginner mode is on by default; persisted in localStorage qc_beginner. */
  beginner: boolean;
  setBeginner: (value: boolean) => void;
  toggleBeginner: () => void;
  /** ⌘K command palette (owned by App). */
  commandOpen: boolean;
  setCommandOpen: (open: boolean) => void;
  /** Two-step onboarding dialog (optional, opened from Home / palette). */
  onboardingOpen: boolean;
  openOnboarding: () => void;
  closeOnboarding: () => void;
}

export const useUIStore = create<UIState>()((set, get) => ({
  beginner: typeof localStorage === "undefined" ? true : readBeginner(),
  setBeginner: (beginner) => {
    try { localStorage.setItem(BEGINNER_KEY, beginner ? "1" : "0"); } catch { /* ignore */ }
    set({ beginner });
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("qc-beginner", { detail: { beginner } }));
    }
  },
  toggleBeginner: () => get().setBeginner(!get().beginner),
  commandOpen: false,
  setCommandOpen: (commandOpen) => set({ commandOpen }),
  onboardingOpen: false,
  openOnboarding: () => set({ onboardingOpen: true }),
  closeOnboarding: () => set({ onboardingOpen: false }),
}));

/** Subscribe to beginner mode from any page: `const beginner = useBeginner()`. */
export function useBeginner(): boolean {
  return useUIStore((state) => state.beginner);
}

/** Imperative helper for event handlers outside React. */
export function setBeginner(value: boolean): void {
  useUIStore.getState().setBeginner(value);
}

export function getBeginner(): boolean {
  return useUIStore.getState().beginner;
}

export function toggleBeginner(): void {
  useUIStore.getState().toggleBeginner();
}
