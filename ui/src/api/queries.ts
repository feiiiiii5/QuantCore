import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const qk = {
  health: ["health"] as const,
  meta: ["meta"] as const,
  overview: (snapshot?: string) => ["market", "overview", snapshot ?? "latest"] as const,
  securities: (query: string) => ["market", "securities", query] as const,
  bars: (code: string | null, snapshot?: string) => ["market", "bars", code ?? "", snapshot ?? "latest"] as const,
  templates: ["strategies", "templates"] as const,
  screenerPresets: ["screener", "presets"] as const,
  experiments: (limit: number) => ["experiments", limit] as const,
  experiment: (id: string) => ["experiments", "detail", id] as const,
  experimentResult: (id: string) => ["experiments", "result", id] as const,
  data: ["data", "status"] as const,
  providers: ["data", "providers"] as const,
  quality: (snapshot: string) => ["data", "quality", snapshot] as const,
  jobs: (status?: string) => ["jobs", status ?? "all"] as const,
};

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: api.health, staleTime: 30_000 });
}
export function useMeta() {
  return useQuery({ queryKey: qk.meta, queryFn: api.meta, staleTime: 30_000 });
}
export function useOverview(snapshot?: string) {
  return useQuery({ queryKey: qk.overview(snapshot), queryFn: () => api.overview(snapshot), staleTime: 15_000 });
}
export function useSecurities(query = "", limit = 300) {
  return useQuery({ queryKey: qk.securities(`${query}:${limit}`), queryFn: () => api.securities(query, limit), staleTime: 15_000 });
}
export function useBars(code: string | null, snapshot?: string) {
  return useQuery({ queryKey: qk.bars(code, snapshot), queryFn: () => api.bars(code ?? "", snapshot), enabled: Boolean(code) });
}
export function useScreenerPresets() {
  return useQuery({ queryKey: qk.screenerPresets, queryFn: api.screenerPresets, staleTime: 60_000 });
}
export function useTemplates() {
  return useQuery({ queryKey: qk.templates, queryFn: api.templates, staleTime: 60_000 });
}
export function useExperiments(limit = 100) {
  return useQuery({ queryKey: qk.experiments(limit), queryFn: () => api.experiments(limit) });
}
export function useExperimentDetail(id: string | null) {
  return useQuery({ queryKey: qk.experiment(id ?? ""), queryFn: () => api.experiment(id ?? ""), enabled: Boolean(id) });
}
export function useExperimentResult(id: string | null) {
  return useQuery({ queryKey: qk.experimentResult(id ?? ""), queryFn: () => api.experimentResult(id ?? ""), enabled: Boolean(id) });
}
export function useDataStatus() {
  return useQuery({ queryKey: qk.data, queryFn: api.dataStatus });
}
export function useProviders() {
  return useQuery({ queryKey: qk.providers, queryFn: api.providers, staleTime: 60_000 });
}
export function useQuality(snapshot: string | null) {
  return useQuery({ queryKey: qk.quality(snapshot ?? ""), queryFn: () => api.quality(snapshot ?? ""), enabled: Boolean(snapshot) });
}
export function useJobs(status?: string) {
  return useQuery({ queryKey: qk.jobs(status), queryFn: () => api.jobs(status), refetchInterval: 5000 });
}

export function useRunScreener() {
  return useMutation({ mutationFn: api.runScreener });
}
export function useValidateStrategy() {
  return useMutation({ mutationFn: ({ template, params }: { template: string; params: Record<string, unknown> }) => api.validateStrategy(template, params) });
}
export function useSubmitBacktest() {
  return useMutation({ mutationFn: api.submitBacktest });
}
export function useCancelJob() {
  return useMutation({ mutationFn: api.cancelJob });
}
export function useReplayExperiment() {
  return useMutation({ mutationFn: api.replayExperiment });
}
export function useCompareExperiments() {
  return useMutation({ mutationFn: api.compareExperiments });
}
export function useUpdateData() {
  return useMutation({ mutationFn: api.updateData });
}
export function useBuildSnapshot() {
  return useMutation({ mutationFn: api.buildSnapshot });
}
export function useBootstrap() {
  return useMutation({ mutationFn: api.bootstrap });
}
export function useFactor() {
  return useMutation({ mutationFn: api.factor });
}
export function useSweep() {
  return useMutation({ mutationFn: api.sweep });
}
export function useWalkForward() {
  return useMutation({ mutationFn: api.walkForward });
}
export function useAttribution() {
  return useMutation({ mutationFn: api.attribution });
}
export function useDeleteExperiment() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.deleteExperiment,
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["experiments"] }); },
  });
}
