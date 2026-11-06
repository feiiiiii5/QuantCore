import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FlaskConical, Plus, ShieldCheck, Sparkles, X } from "lucide-react";
import {
  useBootstrap, useCompleteOnboardingStep, useDataIntegrity, useExperiments, useSecurities,
  useLiveIndices, useLiveQuotes, useLiveStatus, useOnboarding, useOverview, useSaveWatchlist, useWatchlist,
} from "../api/queries";
import type { OnboardingStep } from "../api/types";
import {
  Badge, Button, Callout, EmptyState, Input, List, ListRow, PageHeader, Panel, QuoteRow, Skeleton, Sparkline, StepList,
} from "../components";
import { compact, dateInt, num, pct, signedPct } from "../lib/format";
import { changeTone, indexViews, integrityLabel, integrityTone, liveSummary, liveTone } from "../lib/live";
import { notify } from "../lib/notify";
import { useBeginner, useUIStore } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const DOT_CLASS: Record<string, string> = { live: "dot live pulse", closed: "dot closed", offline: "dot offline", error: "dot error" };

const FALLBACK_STEPS: OnboardingStep[] = [
  { id: "data", title: t.home.steps.bootstrap, description: t.home.stepDescriptions.data, action: "bootstrap", label: t.home.stepActions.bootstrap, done: false },
  { id: "backtest", title: t.home.steps.backtest, description: t.home.stepDescriptions.backtest, action: "backtest", label: t.home.stepActions.backtest, done: false },
  { id: "result", title: t.home.steps.browse, description: t.home.stepDescriptions.result, action: "browse", label: t.home.stepActions.browse, done: false },
  { id: "data_health", title: t.home.steps.data, description: t.home.stepDescriptions.dataHealth, action: "data", label: t.home.stepActions.data, done: false },
];

function fallbackSpark(values: number[], close: number | null): number[] {
  if (values.length) return values;
  return close != null ? [close, close] : [];
}

export default function HomePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const beginner = useBeginner();
  const openOnboarding = useUIStore((state) => state.openOnboarding);
  const status = useLiveStatus();
  const liveEnabled = Boolean(status.data?.enabled);
  const liveIndices = useLiveIndices(liveEnabled);
  const overview = useOverview();
  const watchlist = useWatchlist();
  const codes = watchlist.data?.codes ?? [];
  const liveQuotes = useLiveQuotes(codes, liveEnabled);
  const securities = useSecurities("", 1000, codes, codes.length > 0);
  const onboarding = useOnboarding();
  const completeStep = useCompleteOnboardingStep();
  const bootstrap = useBootstrap();
  const experiments = useExperiments(6);
  const integrity = useDataIntegrity();
  const saveWatchlist = useSaveWatchlist();
  const [addCode, setAddCode] = useState("");
  const [addError, setAddError] = useState("");

  const views = useMemo(() => indexViews(liveIndices.data?.quotes, overview.data?.indices), [liveIndices.data, overview.data]);
  const tone = liveTone(status.data);
  const quoteByCode = useMemo(() => new Map((liveQuotes.data?.quotes ?? []).map((quote) => [quote.code, quote])), [liveQuotes.data]);
  const securityByCode = useMemo(() => new Map((securities.data ?? []).map((row) => [row.code, row])), [securities.data]);
  const steps = onboarding.data?.steps?.length ? onboarding.data.steps : FALLBACK_STEPS;
  const firstIncomplete = steps.find((step) => !step.done);

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["data"] });
    void queryClient.invalidateQueries({ queryKey: ["experiments"] });
    void queryClient.invalidateQueries({ queryKey: ["market"] });
    void queryClient.invalidateQueries({ queryKey: ["onboarding"] });
  };
  const runBootstrap = async () => {
    try {
      const result = await bootstrap.mutateAsync({ n_sec: 40, start: "2022-01-04", end: "2024-12-31", seed: 42 });
      const snapshot = typeof result.snapshot === "string" ? result.snapshot : "";
      void completeStep.mutateAsync("data").catch(() => undefined);
      notify({ kind: "success", title: t.home.bootstrapDone, body: snapshot ? `快照 ${snapshot}` : undefined });
      refreshAll();
    } catch (reason) {
      notify({ kind: "error", title: t.home.bootstrapFailed, body: reason instanceof Error ? reason.message : undefined });
    }
  };
  const onStepAction = (id: string) => {
    const step = steps.find((item) => item.id === id);
    if (!step) return;
    if (step.action === "bootstrap") { openOnboarding(); return; }
    if (step.action === "backtest") { navigate("/backtest"); return; }
    if (step.action === "browse") { navigate("/experiments"); return; }
    navigate("/data");
  };
  const addToWatchlist = () => {
    const code = addCode.trim();
    if (!/^\d{6}$/.test(code)) { setAddError(t.home.watchlistAddHint); return; }
    if (codes.includes(code)) { setAddError(t.home.watchlistExists); return; }
    setAddError("");
    saveWatchlist.mutate([...codes, code], {
      onSuccess: () => { setAddCode(""); notify({ kind: "success", title: `${t.home.watchlistAdded} ${code}` }); },
      onError: (reason) => setAddError(reason.message),
    });
  };
  const removeFromWatchlist = (code: string) => {
    saveWatchlist.mutate(codes.filter((item) => item !== code), {
      onSuccess: () => notify({ kind: "info", title: t.home.watchlistRemoved, body: code }),
      onError: (reason) => notify({ kind: "error", title: t.home.watchlistAddFailed, body: reason.message }),
    });
  };

  const integrityStatus = integrity.data?.status;
  const integrityToneValue = integrityTone(integrityStatus);
  const integrityBadgeTone = integrityToneValue === "ok" ? "ok" : integrityToneValue === "danger" ? "danger" : "warn";
  const failingChecks = (integrity.data?.checks ?? []).filter((check) => check.status !== "pass");
  const latest = experiments.data?.[0] ?? null;

  return (
    <div className="page">
      <PageHeader
        title={t.home.title}
        subtitle="今天先做什么：看市场状态、自选与新手进度，然后开始一次可复现的研究。"
        actions={(
          <>
            <Button variant="secondary" icon={Sparkles} onClick={openOnboarding}>一键示例</Button>
            <Button variant="primary" icon={ArrowRight} href="/backtest">开始一次研究</Button>
          </>
        )}
      />

      <Panel
        title={<><span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />{t.home.marketBand}</>}
        subtitle={t.home.marketBandHint}
        actions={<Button variant="ghost" size="sm" iconRight={ArrowRight} href="/market">行情</Button>}
      >
        {overview.isLoading && !views.some((view) => view.close != null) ? <Skeleton variant="tile" rows={1} height={110} /> : (
          <div className="grid grid-4">
            {views.map((view) => (
              <div className="index-card" key={view.key}>
                <div className="index-top">
                  <h3>{view.name}</h3>
                  <span className={changeTone(view.changePct)}>{signedPct(view.changePct == null ? null : view.changePct / 100)}</span>
                </div>
                <div className="kpi-value">{view.close == null ? "—" : num(view.close)}</div>
                <Sparkline values={fallbackSpark(view.spark, view.close)} positive={(view.changePct ?? 0) >= 0} height={30} />
                <small>{view.source === "live" ? t.appbar.live : view.source === "snapshot" ? t.common.snapshot : t.common.notAvailable}</small>
              </div>
            ))}
          </div>
        )}
        <div className="row" style={{ marginTop: "var(--sp-5)" }}>
          <span className="live-state"><span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />{status.data?.enabled ? liveSummary(status.data, overview.data?.as_of ?? null) : status.data ? "实时行情未开启" : "本地服务离线"}</span>
          {status.data && !liveEnabled ? <Button variant="ghost" size="sm" href="/settings">{t.home.liveOffHint}</Button> : null}
          <span className="spacer" />
          {overview.data ? <span className="page-note-sm">快照 {overview.data.snapshot.id ?? "—"} · {dateInt(overview.data.snapshot.end)}</span> : null}
        </div>
      </Panel>

      <div className="grid grid-2">
        <Panel
          title={t.home.watchlist}
          subtitle={t.home.watchlistHint}
          actions={liveEnabled ? <Badge tone="ok" dot>{t.appbar.live}</Badge> : <Badge tone="warn" dot>{t.market.offlineSnapshot}</Badge>}
          bodyClassName="home-watchlist-body"
        >
          <div className="stack">
            <div className="row">
              <Input value={addCode} onChange={(event) => { setAddCode(event.target.value); setAddError(""); }} onKeyDown={(event) => { if (event.key === "Enter") addToWatchlist(); }} placeholder={t.home.watchlistPlaceholder} aria-label={t.home.watchlistPlaceholder} inputMode="numeric" style={{ flex: "1 1 160px" }} />
              <Button variant="secondary" icon={Plus} onClick={addToWatchlist} loading={saveWatchlist.isPending}>{t.home.watchlistAdd}</Button>
            </div>
            {addError ? <p className="error-text" role="alert">{addError}</p> : null}
            {watchlist.isLoading ? <Skeleton rows={3} /> : null}
            {watchlist.isError ? <EmptyState compact title={t.emptyStates.serviceOffline} hint={watchlist.error.message} action={<Button variant="secondary" size="sm" href="/settings">{t.common.openSettings}</Button>} /> : null}
            {!watchlist.isLoading && !watchlist.isError && codes.length === 0 ? (
              <EmptyState compact title={t.home.watchlistEmpty} hint={t.home.watchlistEmptyHint} action={<Button variant="secondary" size="sm" href="/market">{t.nav.market}</Button>} />
            ) : null}
            {codes.length > 0 ? (
              <div className="stack-tight">
                {codes.map((code) => {
                  const quote = quoteByCode.get(code);
                  const row = securityByCode.get(code);
                  return (
                    <QuoteRow
                      key={code}
                      code={code}
                      name={quote?.name || row?.name || code}
                      price={quote?.price ?? row?.last ?? null}
                      changePct={quote?.change_pct ?? row?.change_pct ?? null}
                      amount={quote?.amount ?? null}
                      loading={liveEnabled && liveQuotes.isLoading}
                      onClick={() => navigate(`/market?code=${encodeURIComponent(code)}`)}
                      badge={(
                        <button type="button" className="icon-btn icon-btn-sm" aria-label={`移除 ${code}`} onClick={(event) => { event.stopPropagation(); removeFromWatchlist(code); }}>
                          <X size={14} />
                        </button>
                      )}
                    />
                  );
                })}
              </div>
            ) : null}
          </div>
        </Panel>

        <Panel
          title={t.home.onboarding}
          subtitle={onboarding.data ? `${t.home.onboardingDone} ${onboarding.data.progress.done}/${onboarding.data.progress.total}` : t.home.onboardingHint}
          actions={firstIncomplete ? (
            <Button variant="primary" size="sm" icon={Sparkles} loading={bootstrap.isPending} onClick={() => onStepAction(firstIncomplete.id)}>
              {firstIncomplete.action === "bootstrap" ? t.home.bootstrap : t.common.next}
            </Button>
          ) : <Badge tone="ok" dot>{t.common.done}</Badge>}
        >
          <div className="stack">
            {onboarding.isError ? <p className="page-note-sm">{t.home.onboardingUnavailable}</p> : null}
            <StepList
              compact
              steps={steps.map((step) => ({ id: step.id, title: step.title, description: step.description, done: step.done, actionLabel: step.done ? undefined : step.label }))}
              onAction={onStepAction}
            />
            <div className="row">
              <Button variant="secondary" size="sm" icon={Sparkles} loading={bootstrap.isPending} onClick={() => void runBootstrap()}>{bootstrap.isPending ? t.home.bootstrapRunning : t.home.bootstrap}</Button>
              <Button variant="ghost" size="sm" href="/data">{t.nav.data}</Button>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid grid-2">
        <Panel
          title={t.home.recent}
          subtitle={t.home.recentHint}
          actions={<Button variant="ghost" size="sm" iconRight={ArrowRight} href="/experiments">{t.home.viewExperiments}</Button>}
        >
          {experiments.isLoading ? <Skeleton rows={3} height={56} /> : null}
          {experiments.isError ? <EmptyState compact title={t.emptyStates.serviceOffline} hint={experiments.error.message} action={<Button variant="secondary" size="sm" onClick={() => void experiments.refetch()}>{t.common.retry}</Button>} /> : null}
          {!experiments.isLoading && !experiments.isError && (experiments.data ?? []).length === 0 ? (
            <EmptyState compact title={t.home.recentEmpty} hint={t.home.recentEmptyHint} action={<Button variant="primary" size="sm" icon={Sparkles} onClick={openOnboarding}>{t.home.bootstrap}</Button>} />
          ) : null}
          {(experiments.data ?? []).length > 0 ? (
            <List inset>
              {(experiments.data ?? []).slice(0, 6).map((experiment) => {
                const metrics = experiment.metrics;
                return (
                  <ListRow
                    key={experiment.run_id}
                    href={`/experiments?run=${encodeURIComponent(experiment.run_id)}`}
                    leading={<FlaskConical size={16} aria-hidden="true" />}
                    title={experiment.strategy_name || experiment.template || "回测"}
                    subtitle={`${experiment.created_at ? new Date(experiment.created_at).toLocaleString("zh-CN", { hour12: false }) : "—"}${experiment.snapshot_id ? ` · 快照 ${experiment.snapshot_id.slice(0, 14)}` : ""}`}
                    trailing={(
                      <div className="row row-tight">
                        <Badge tone={experiment.synthetic ? "warn" : "ok"}>{experiment.synthetic ? "SYNTHETIC" : t.common.real}</Badge>
                        <Badge tone={(metrics?.total_return ?? 0) >= 0 ? "up" : "down"}>{pct(metrics?.total_return)}</Badge>
                      </div>
                    )}
                  />
                );
              })}
            </List>
          ) : null}
        </Panel>

        <Panel
          title={t.home.integrity}
          subtitle={t.home.integrityHint}
          tone={integrity.data ? (integrityToneValue === "ok" ? "ok" : integrityToneValue === "danger" ? "danger" : "warn") : "neutral"}
          actions={<Button variant="ghost" size="sm" iconRight={ArrowRight} href="/data">{t.home.viewData}</Button>}
        >
          {integrity.isLoading ? <Skeleton rows={3} height={48} /> : null}
          {integrity.isError ? <EmptyState compact icon={ShieldCheck} title={t.integrity.notRun} hint={integrity.error.message} action={<Button variant="secondary" size="sm" href="/data">{t.integrity.runHint}</Button>} /> : null}
          {integrity.data ? (
            <div className="stack">
              <div className="row">
                <Badge tone={integrityBadgeTone} dot>{integrityLabel(integrity.data.status)}</Badge>
                <span className="page-note-sm">{integrity.data.snapshot ? `快照 ${integrity.data.snapshot.id.slice(0, 16)} · ${integrity.data.snapshot.synthetic ? t.integrity.snapshotSynthetic : t.common.real} · ${dateInt(integrity.data.snapshot.end)}` : t.home.integrityEmpty}</span>
              </div>
              <div className="grid grid-4">
                <div className="stat-tile sm"><div className="stat-tile-label">{t.integrity.coverage}</div><div className="stat-tile-value">{num(integrity.data.coverage.coverage_pct)}%</div></div>
                <div className="stat-tile sm"><div className="stat-tile-label">{t.integrity.symbols}</div><div className="stat-tile-value">{compact(integrity.data.coverage.symbols)}</div></div>
                <div className="stat-tile sm"><div className="stat-tile-label">{t.integrity.days}</div><div className="stat-tile-value">{compact(integrity.data.coverage.trading_days)}</div></div>
                <div className="stat-tile sm"><div className="stat-tile-label">{t.integrity.gaps}</div><div className="stat-tile-value">{compact(integrity.data.gaps.missing_days)}</div></div>
              </div>
              {failingChecks.length ? (
                <Callout tone="warn" title={t.integrity.checks}>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {failingChecks.slice(0, 4).map((check) => <li key={check.id}>{check.title}：{check.detail}</li>)}
                  </ul>
                </Callout>
              ) : <p className="success-text"><CheckCircle2 size={13} /> {t.home.integrityAllPass}</p>}
            </div>
          ) : null}
        </Panel>
      </div>

      {beginner ? (
        <Panel title={t.home.guideTitle} dense>
          <ul className="hint-list">
            <li>{t.home.guide1}</li>
            <li>{t.home.guide2}</li>
            <li>{t.home.guide3}</li>
          </ul>
          <p className="page-note-sm" style={{ marginTop: "var(--sp-4)" }}>{t.disclaimer}</p>
        </Panel>
      ) : null}
      {latest ? <p className="page-note-sm">最近一次研究：{latest.strategy_name || latest.template || latest.run_id} · {latest.created_at.slice(0, 10)}</p> : null}
    </div>
  );
}
