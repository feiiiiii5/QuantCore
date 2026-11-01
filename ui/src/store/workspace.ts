import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export interface BacktestDraft {
  template: string;
  paramsText: string;
  start: string;
  end: string;
  cash: string;
  exec: string;
  commissionRate: string;
  minCommission: string;
  stampDutyRate: string;
  slippageBps: string;
  maxParticipation: string;
  minRebalanceValue: string;
  trace: string;
  seed: string;
  benchmarkCode: string;
}

interface WorkspaceState {
  lastPath: string;
  marketCode: string;
  marketQuery: string;
  screenerExpression: string;
  screenerPreset: string;
  backtestDraft: Partial<BacktestDraft>;
  notes: Record<string, string>;
  tags: Record<string, string[]>;
  setLastPath: (path: string) => void;
  setMarketCode: (code: string) => void;
  setMarketQuery: (query: string) => void;
  setScreenerDraft: (draft: { expression?: string; preset?: string }) => void;
  setBacktestDraft: (draft: Partial<BacktestDraft>) => void;
  setNote: (runId: string, note: string) => void;
  setTags: (runId: string, tags: string[]) => void;
}

export const useWorkspace = create<WorkspaceState>()(
  persist(
    (set) => ({
      lastPath: "/",
      marketCode: "",
      marketQuery: "",
      screenerExpression: "",
      screenerPreset: "",
      backtestDraft: {},
      notes: {},
      tags: {},
      setLastPath: (lastPath) => set({ lastPath }),
      setMarketCode: (marketCode) => set({ marketCode }),
      setMarketQuery: (marketQuery) => set({ marketQuery }),
      setScreenerDraft: ({ expression, preset }) => set((state) => ({
        screenerExpression: expression ?? state.screenerExpression,
        screenerPreset: preset ?? state.screenerPreset,
      })),
      setBacktestDraft: (draft) => set((state) => ({ backtestDraft: { ...state.backtestDraft, ...draft } })),
      setNote: (runId, note) => set((state) => ({ notes: { ...state.notes, [runId]: note } })),
      setTags: (runId, tags) => set((state) => ({ tags: { ...state.tags, [runId]: tags } })),
    }),
    { name: "qc_workspace_v1", storage: createJSONStorage(() => localStorage) },
  ),
);
