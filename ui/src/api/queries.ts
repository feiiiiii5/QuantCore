import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const qk = {
  health: ["health"] as const,
  meta: ["meta"] as const,
  doctor: ["doctor"] as const,
  overview: (snapshot?: string) => ["market", "overview", snapshot ?? "latest"] as const,
  securities: (query: string) => ["market", "securities", query] as const,
  securityProfile: (code: string) => ["market", "profile", code] as const,
  financials: (code: string) => ["market", "financials", code] as const,
  bars: (code: string | null, snapshot?: string) => ["market", "bars", code ?? "", snapshot ?? "latest"] as const,
  minuteBars: (code: string | null) => ["market", "minute-bars", code ?? ""] as const,
  templates: ["strategies", "templates"] as const,
  plugins: ["strategies", "plugins"] as const,
  screenerPresets: ["screener", "presets"] as const,
  experiments: (limit: number) => ["experiments", limit] as const,
  experiment: (id: string) => ["experiments", "detail", id] as const,
  experimentResult: (id: string) => ["experiments", "result", id] as const,
  data: ["data", "status"] as const,
  dataCatalog: ["data", "catalog"] as const,
  providers: ["data", "providers"] as const,
  quality: (snapshot: string) => ["data", "quality", snapshot] as const,
  jobs: (status?: string) => ["jobs", status ?? "all"] as const,
  liveStatus: ["live", "status"] as const,
  liveIndices: ["live", "indices"] as const,
  liveQuotes: (codes: string[]) => ["live", "quotes", codes.join(",")] as const,
  watchlist: ["live", "watchlist"] as const,
  dataIntegrity: (snapshot?: string) => ["data", "integrity", snapshot ?? "latest"] as const,
  onboarding: ["onboarding"] as const,
  onboardingPresets: ["onboarding", "presets"] as const,
};

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: api.health, staleTime: 30_000 });
}
export function useMeta() {
  return useQuery({ queryKey: qk.meta, queryFn: api.meta, staleTime: 30_000 });
}
/** Manual only: local self-check runs when the settings card asks for it. */
export function useDoctor() {
  return useQuery({ queryKey: qk.doctor, queryFn: () => api.doctor(), enabled: false, retry: false, staleTime: 60_000 });
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
export function useMinuteBars(code: string | null, enabled = true) {
  return useQuery({ queryKey: qk.minuteBars(code), queryFn: () => api.minuteBars(code ?? ""), enabled: Boolean(code) && enabled, staleTime: 60_000 });
}
export function useFinancials(code: string | null) {
  return useQuery({ queryKey: qk.financials(code ?? ""), queryFn: () => api.financials(code ?? ""), enabled: Boolean(code), staleTime: 60_000 });
}
export function useSecurityProfile(code: string | null) {
  return useQuery({ queryKey: qk.securityProfile(code ?? ""), queryFn: () => api.securityProfile(code ?? ""), enabled: Boolean(code), staleTime: 60_000 });
}
export function useScreenerPresets() {
  return useQuery({ queryKey: qk.screenerPresets, queryFn: api.screenerPresets, staleTime: 60_000 });
}
export function useTemplates() {
  return useQuery({ queryKey: qk.templates, queryFn: api.templates, staleTime: 60_000 });
}
export function usePlugins() {
  return useQuery({ queryKey: qk.plugins, queryFn: api.plugins, staleTime: 15_000 });
}
export function useValidatePlugin() {
  return useMutation({ mutationFn: api.validatePlugin });
}
export function useRunPlugin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, payload }: { name: string; payload: Record<string, unknown> }) => api.runPlugin(name, payload),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["jobs"] }); },
  });
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
export function useDataCatalog() {
  return useQuery({ queryKey: qk.dataCatalog, queryFn: api.dataCatalog, staleTime: 60_000 });
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
export function useFactorCorrelation() {
  return useMutation({ mutationFn: api.factorCorrelation });
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

export function usePaperPortfolio() {
  return useMutation({ mutationFn: api.paperPortfolio });
}
export function useOverfitting() {
  return useMutation({ mutationFn: api.overfitting });
}
export function usePBO() {
  return useMutation({ mutationFn: api.pbo });
}
export function useCostSensitivity() {
  return useMutation({ mutationFn: api.costSensitivity });
}
export function useMonteCarlo() {
  return useMutation({ mutationFn: api.monteCarlo });
}
export function useCapacity() {
  return useMutation({ mutationFn: api.capacity });
}

// ---------------------------------------------------------------- live market / beginner flow

/** Server-side live status (polled); keeps the UI honest about offline/synthetic modes. */
export function useLiveStatus() {
  return useQuery({ queryKey: qk.liveStatus, queryFn: api.liveStatus, refetchInterval: 5_000, staleTime: 2_000, retry: false });
}
export function useLiveIndices(enabled = true) {
  return useQuery({ queryKey: qk.liveIndices, queryFn: api.liveIndices, refetchInterval: 5_000, staleTime: 2_000, retry: false, enabled });
}
export function useLiveQuotes(codes: string[], enabled = true) {
  return useQuery({
    queryKey: qk.liveQuotes(codes),
    queryFn: () => api.liveQuotes(codes),
    refetchInterval: 5_000,
    staleTime: 2_000,
    retry: false,
    enabled: enabled && codes.length > 0,
  });
}
export function useWatchlist() {
  return useQuery({ queryKey: qk.watchlist, queryFn: api.watchlist, staleTime: 30_000 });
}
export function useSaveWatchlist() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.saveWatchlist,
    onSuccess: () => { void client.invalidateQueries({ queryKey: qk.watchlist }); },
  });
}
export function useDataIntegrity(snapshot?: string) {
  return useQuery({ queryKey: qk.dataIntegrity(snapshot), queryFn: () => api.dataIntegrity(snapshot), staleTime: 60_000 });
}
export function useOnboarding() {
  return useQuery({ queryKey: qk.onboarding, queryFn: api.onboarding, staleTime: 10_000 });
}
export function useCompleteOnboardingStep() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.completeOnboardingStep,
    onSuccess: () => { void client.invalidateQueries({ queryKey: qk.onboarding }); },
  });
}
export function useOnboardingPresets() {
  return useQuery({ queryKey: qk.onboardingPresets, queryFn: api.onboardingPresets, staleTime: 60_000 });
}
