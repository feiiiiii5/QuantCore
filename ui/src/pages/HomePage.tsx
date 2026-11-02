import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, BarChart3, CheckCircle2, Database, FlaskConical, Plus, RefreshCw, ShieldCheck, Sparkles, X,
} from "lucide-react";
import { api } from "../api/client";
import {
  qk, useBootstrap, useCompleteOnboardingStep, useDataIntegrity, useExperiments,
  useLiveIndices, useLiveQuotes, useLiveStatus, useOnboarding, useOverview, useSaveWatchlist, useWatchlist,
} from "../api/queries";
import type { OnboardingStep } from "../api/types";
import {
  Badge, EmptyState, MetricPill, Panel, QuoteRow, Skeleton, Sparkline, StepList,
} from "../components";
import { compact, dateInt, num, pct, signedPct } from "../lib/format";
import { changeTone, indexViews, integrityLabel, integrityTone, liveSummary, liveTone } from "../lib/live";
import { notify } from "../lib/notify";
import { useBeginner } from "../store/ui";
import { zhCN as t } from "../i18n/zh-CN";

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
  const status = useLiveStatus();
  const liveEnabled = Boolean(status.data?.enabled);
  const liveIndices = useLiveIndices(liveEnabled);
  const overview = useOverview();
  const watchlist = useWatchlist();
  const codes = watchlist.data?.codes ?? [];
  const liveQuotes = useLiveQuotes(codes, liveEnabled);
  const securities = useQuery({
    queryKey: qk.securities("home-watch:1000"),
    queryFn: () => api.securities("", 1000),
    enabled: codes.length > 0,
    staleTime: 60_000,
    retry: false,
  });
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
    if (step.action === "bootstrap") { void runBootstrap(); return; }
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

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{t.home.title}</h1>
          <p>{t.home.subtitle}</p>
        </div>
        <div className="page-head-actions">
          <Link className="btn primary" to="/backtest"><BarChart3 size={15} /> {t.home.cta}</Link>
        </div>
      </header>

      <Panel
        title={<><span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />{t.home.marketBand}</>}
        subtitle={t.home.marketBandHint}
        actions={<Link className="btn sm" to="/market">{t.nav.market} <ArrowRight size={13} /></Link>}
      >
        {overview.isLoading && !views.some((view) => view.close != null) ? <Skeleton variant="tile" rows={1} height={110} /> : (
          <div className="grid kpis home-index-grid">
            {views.map((view) => (
              <div className="index-card" key={view.key}>
                <div className="index-top">
                  <h3>{view.name}</h3>
                  <span className={changeTone(view.changePct)}>{signedPct(view.changePct == null ? null : view.changePct / 100)}</span>
                </div>
                <div className="kpi">{view.close == null ? "—" : num(view.close)}</div>
                <Sparkline values={fallbackSpark(view.spark, view.close)} positive={(view.changePct ?? 0) >= 0} height={30} />
                <small className="muted">
                  {view.source === "live" ? t.appbar.live : view.source === "snapshot" ? t.common.snapshot : t.common.notAvailable}
                </small>
              </div>
            ))}
          </div>
        )}
        <div className="row" style={{ marginTop: "var(--sp-2)" }}>
          <span className="live-state">
            <span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />
            {status.data?.enabled ? liveSummary(status.data, overview.data?.as_of ?? null) : status.data ? "实时行情未开启" : "本地服务离线"}
          </span>
          {status.data && !liveEnabled ? <Link className="link-btn" to="/settings">{t.home.liveOffHint}</Link> : null}
          <span className="spacer" />
          {overview.data ? <span className="muted small">快照 {overview.data.snapshot.id ?? "—"} · {dateInt(overview.data.snapshot.end)}</span> : null}
        </div>
      </Panel>

      <div className="grid two-col">
        <Panel
          title={<><Sparkles size={14} aria-hidden="true" />{t.home.watchlist}</>}
          subtitle={t.home.watchlistHint}
          actions={liveEnabled ? <Badge tone="ok" dot>{t.appbar.live}</Badge> : <Badge tone="warn" dot>{t.market.offlineSnapshot}</Badge>}
        >
          <div className="row" style={{ marginBottom: "var(--sp-2)" }}>
            <input
              className="input"
              value={addCode}
              onChange={(event) => { setAddCode(event.target.value); setAddError(""); }}
              onKeyDown={(event) => { if (event.key === "Enter") addToWatchlist(); }}
              placeholder={t.home.watchlistPlaceholder}
              aria-label={t.home.watchlistPlaceholder}
              inputMode="numeric"
              style={{ flex: "1 1 140px" }}
            />
            <button className="btn" onClick={addToWatchlist} disabled={saveWatchlist.isPending}>
              <Plus size={14} /> {t.home.watchlistAdd}
            </button>
          </div>
          {addError ? <p className="error" role="alert">{addError}</p> : null}
          {watchlist.isLoading ? <Skeleton rows={3} /> : null}
          {watchlist.isError ? (
            <EmptyState compact icon={Database} title={t.emptyStates.serviceOffline} hint={watchlist.error.message} action={<Link className="btn sm" to="/settings">{t.common.openSettings}</Link>} />
          ) : null}
          {!watchlist.isLoading && !watchlist.isError && codes.length === 0 ? (
            <EmptyState compact title={t.home.watchlistEmpty} hint={t.home.watchlistEmptyHint} action={<Link className="btn sm" to="/market">{t.nav.market}</Link>} />
          ) : null}
          {codes.length > 0 ? (
            <div className="stack tight">
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
                      <button
                        type="button"
                        className="icon-btn"
                        style={{ width: 24, height: 24 }}
                        aria-label={`移除 ${code}`}
                        onClick={(event) => { event.stopPropagation(); removeFromWatchlist(code); }}
                      >
                        <X size={12} />
                      </button>
                    )}
                  />
                );
              })}
            </div>
          ) : null}
        </Panel>

        <Panel
          title={<><CheckCircle2 size={14} aria-hidden="true" />{t.home.onboarding}</>}
          subtitle={onboarding.data ? `${t.home.onboardingDone} ${onboarding.data.progress.done}/${onboarding.data.progress.total}` : t.home.onboardingHint}
          actions={firstIncomplete ? (
            <button className="btn primary sm" onClick={() => onStepAction(firstIncomplete.id)} disabled={bootstrap.isPending}>
              {bootstrap.isPending ? <RefreshCw className="spin" size={13} /> : <Sparkles size={13} />}
              {firstIncomplete.action === "bootstrap" ? t.home.bootstrap : t.common.next}
            </button>
          ) : <Badge tone="ok" dot>{t.common.done}</Badge>}
        >
          {onboarding.isError ? <p className="hint-text" style={{ marginBottom: "var(--sp-2)" }}>{t.home.onboardingUnavailable}</p> : null}
          <StepList
            compact
            steps={steps.map((step) => ({
              id: step.id,
              title: step.title,
              description: step.description,
              done: step.done,
              actionLabel: step.done ? undefined : step.label,
            }))}
            onAction={onStepAction}
          />
          <div className="row" style={{ marginTop: "var(--sp-2)" }}>
            <button className="btn sm" onClick={() => void runBootstrap()} disabled={bootstrap.isPending}>
              <Sparkles size={13} /> {bootstrap.isPending ? t.home.bootstrapRunning : t.home.bootstrap}
            </button>
            <Link className="link-btn" to="/data">{t.nav.data}</Link>
          </div>
        </Panel>
      </div>

      <div className="grid two-col">
        <Panel
          title={<><FlaskConical size={14} aria-hidden="true" />{t.home.recent}</>}
          subtitle={t.home.recentHint}
          actions={<Link className="btn sm" to="/experiments">{t.home.viewExperiments} <ArrowRight size={13} /></Link>}
        >
          {experiments.isLoading ? <Skeleton rows={3} height={56} /> : null}
          {experiments.isError ? (
            <EmptyState compact icon={Database} title={t.emptyStates.serviceOffline} hint={experiments.error.message} action={<button className="btn sm" onClick={() => void experiments.refetch()}>{t.common.retry}</button>} />
          ) : null}
          {!experiments.isLoading && !experiments.isError && (experiments.data ?? []).length === 0 ? (
            <EmptyState
              compact
              title={t.home.recentEmpty}
              hint={t.home.recentEmptyHint}
              action={<button className="btn sm primary" onClick={() => void runBootstrap()} disabled={bootstrap.isPending}><Sparkles size={13} /> {t.home.bootstrap}</button>}
            />
          ) : null}
          {(experiments.data ?? []).length > 0 ? (
            <div className="stack tight">
              {(experiments.data ?? []).slice(0, 6).map((experiment) => {
                const metrics = experiment.metrics;
                return (
                  <Link className="research-card" key={experiment.run_id} to={`/experiments?run=${encodeURIComponent(experiment.run_id)}`}>
                    <div className="research-card-head">
                      <strong>{experiment.strategy_name || experiment.template || "回测"}</strong>
                      <span className="row tight">
                        <Badge tone={experiment.synthetic ? "warn" : "ok"}>{experiment.synthetic ? "SYNTHETIC" : t.common.real}</Badge>
                        <Badge tone={integrityBadgeTone}>{integrityLabel(integrityStatus)}</Badge>
                      </span>
                    </div>
                    <div className="row tight">
                      <MetricPill label="总收益" value={metrics ? pct(metrics.total_return) : "—"} tone={metrics && metrics.total_return >= 0 ? "up" : "down"} />
                      <MetricPill label="Sharpe" value={metrics ? metrics.sharpe.toFixed(2) : "—"} />
                      <MetricPill label="最大回撤" value={metrics ? pct(metrics.max_drawdown) : "—"} tone="down" />
                    </div>
                    <div className="muted small">
                      {experiment.created_at ? new Date(experiment.created_at).toLocaleString("zh-CN", { hour12: false }) : "—"}
                      {experiment.snapshot_id ? ` · 快照 ${experiment.snapshot_id}` : ""}
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : null}
        </Panel>

        <Panel
          title={<><ShieldCheck size={14} aria-hidden="true" />{t.home.integrity}</>}
          subtitle={t.home.integrityHint}
          tone={integrity.data ? (integrityToneValue === "ok" ? "ok" : integrityToneValue === "danger" ? "danger" : "warn") : "neutral"}
          actions={<Link className="btn sm" to="/data">{t.home.viewData} <ArrowRight size={13} /></Link>}
        >
          {integrity.isLoading ? <Skeleton rows={3} height={48} /> : null}
          {integrity.isError ? (
            <EmptyState compact icon={ShieldCheck} title={t.integrity.notRun} hint={integrity.error.message} action={<Link className="btn sm" to="/data">{t.integrity.runHint}</Link>} />
          ) : null}
          {integrity.data ? (
            <div className="stack tight">
              <div className="row">
                <Badge tone={integrityBadgeTone} dot>{integrityLabel(integrity.data.status)}</Badge>
                <span className="muted small">
                  {integrity.data.snapshot
                    ? `快照 ${integrity.data.snapshot.id} · ${integrity.data.snapshot.synthetic ? t.integrity.snapshotSynthetic : t.common.real} · ${dateInt(integrity.data.snapshot.end)}`
                    : t.home.integrityEmpty}
                </span>
              </div>
              <div className="grid kpis">
                <div className="stat-tile sm">
                  <div className="stat-tile-label">{t.integrity.coverage}</div>
                  <div className="stat-tile-value">{num(integrity.data.coverage.coverage_pct)}%</div>
                </div>
                <div className="stat-tile sm">
                  <div className="stat-tile-label">{t.integrity.symbols}</div>
                  <div className="stat-tile-value">{compact(integrity.data.coverage.symbols)}</div>
                </div>
                <div className="stat-tile sm">
                  <div className="stat-tile-label">{t.integrity.days}</div>
                  <div className="stat-tile-value">{compact(integrity.data.coverage.trading_days)}</div>
                </div>
                <div className="stat-tile sm">
                  <div className="stat-tile-label">{t.integrity.gaps}</div>
                  <div className="stat-tile-value">{compact(integrity.data.gaps.missing_days)}</div>
                </div>
              </div>
              {failingChecks.length ? (
                <div className="notice warn">
                  <strong>{t.integrity.checks}</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {failingChecks.slice(0, 4).map((check) => (
                      <li key={check.id}>{check.title}：{check.detail}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="success-text"><CheckCircle2 size={13} /> {t.home.integrityAllPass}</p>
              )}
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
          <p className="muted small" style={{ marginTop: "var(--sp-2)" }}>{t.disclaimer}</p>
        </Panel>
      ) : null}
    </div>
  );
}
