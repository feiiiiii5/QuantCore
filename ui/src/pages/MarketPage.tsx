import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowRight, RefreshCw, ShieldCheck, SlidersHorizontal, Star, StarOff } from "lucide-react";
import {
  useBars, useDataIntegrity, useFinancials, useLiveIndices, useLiveQuotes, useLiveStatus,
  useMinuteBars, useOverview, useSaveWatchlist, useSecurities, useSecurityProfile, useWatchlist,
} from "../api/queries";
import type { SecurityRow } from "../api/types";
import {
  Badge, Button, Input, KLineChart, PageHeader, Panel, Segmented, Skeleton, Sparkline, StatePanel, VirtualTable,
} from "../components";
import { compact, dateInt, num, signedPct } from "../lib/format";
import {
  changeTone, indexViews, integrityLabel, integrityTone, liveSummary, liveTone,
  marketReadings, updatedAtLabel,
} from "../lib/live";
import { notify } from "../lib/notify";
import { useChartPalette } from "../theme";
import { useWorkspace } from "../store/workspace";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const DOT_CLASS: Record<string, string> = { live: "dot live pulse", closed: "dot closed", offline: "dot offline", error: "dot error" };

export default function MarketPage() {
  const palette = useChartPalette();
  const [searchParams, setSearchParams] = useSearchParams();
  const overview = useOverview();
  const securitiesQuery = useSecurities("", 1000);
  const rows = securitiesQuery.data ?? [];
  const [picked, setPicked] = useState(() => useWorkspace.getState().marketCode);
  const [query, setQuery] = useState(() => useWorkspace.getState().marketQuery);
  const [listMode, setListMode] = useState<"all" | "watch">("all");
  const [showMA5, setShowMA5] = useState(true);
  const [showMA20, setShowMA20] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const [minuteMode, setMinuteMode] = useState(false);
  const setMarketCode = useWorkspace((state) => state.setMarketCode);
  const setMarketQuery = useWorkspace((state) => state.setMarketQuery);

  const liveStatus = useLiveStatus();
  const liveEnabled = Boolean(liveStatus.data?.enabled);
  const liveIndices = useLiveIndices(liveEnabled);
  const watchlist = useWatchlist();
  const saveWatchlist = useSaveWatchlist();
  const codes = watchlist.data?.codes ?? [];

  const code = searchParams.get("code") || picked || rows[0]?.code || "";
  const bars = useBars(code || null);
  const profile = useSecurityProfile(code || null);
  const financials = useFinancials(code || null);
  const minuteBars = useMinuteBars(code || null, minuteMode);
  const liveQuotes = useLiveQuotes(code ? [code] : [], liveEnabled && Boolean(code));
  const integrity = useDataIntegrity(overview.data?.snapshot.id ?? undefined);

  useEffect(() => {
    if (!code && rows[0]) { setPicked(rows[0].code); setMarketCode(rows[0].code); }
  }, [code, rows, setMarketCode]);
  useEffect(() => { setMarketQuery(query); }, [query, setMarketQuery]);

  const select = useCallback((row: SecurityRow) => {
    setPicked(row.code);
    setMarketCode(row.code);
    setSearchParams({ code: row.code }, { replace: true });
  }, [setMarketCode, setSearchParams]);

  const filtered = useMemo(() => {
    const base = listMode === "watch" ? rows.filter((row) => codes.includes(row.code)) : rows;
    const needle = query.trim().toLowerCase();
    if (!needle) return base;
    return base.filter((row) => `${row.code}${row.name}${row.industry}${row.board}`.toLowerCase().includes(needle));
  }, [codes, listMode, query, rows]);
  const selected = rows.find((row) => row.code === code) ?? null;
  const views = useMemo(() => indexViews(liveIndices.data?.quotes, overview.data?.indices), [liveIndices.data, overview.data]);
  const readings = useMemo(
    () => marketReadings({ quote: liveQuotes.data?.quotes[0] ?? null, bars: bars.data, profile: profile.data }),
    [liveQuotes.data, bars.data, profile.data],
  );
  const tone = liveTone(liveStatus.data);
  const inWatchlist = Boolean(code) && codes.includes(code);

  const refresh = () => {
    void overview.refetch();
    void securitiesQuery.refetch();
    void bars.refetch();
    void profile.refetch();
    void integrity.refetch();
    void liveStatus.refetch();
    if (liveEnabled) void liveQuotes.refetch();
  };
  const toggleWatch = () => {
    if (!code) return;
    const next = inWatchlist ? codes.filter((item) => item !== code) : [...codes, code];
    saveWatchlist.mutate(next, {
      onSuccess: () => notify({ kind: "success", title: inWatchlist ? t.market.removeWatch : t.market.addWatch, body: code }),
      onError: (reason) => notify({ kind: "error", title: t.market.addWatch, body: reason.message }),
    });
  };

  const columns = useMemo<ColumnDef<SecurityRow, unknown>[]>(() => [
    { accessorKey: "code", header: "代码", size: 96, cell: ({ row }) => <span className="mono">{row.original.code}</span> },
    { accessorKey: "name", header: "名称", size: 140, cell: ({ row }) => <span className="truncate" title={row.original.name}>{row.original.name}</span> },
    { accessorKey: "industry", header: "行业", size: 96, cell: ({ row }) => <span className="truncate" title={row.original.industry}>{row.original.industry}</span> },
    { accessorKey: "last", header: "最新", size: 88, cell: ({ row }) => <span className="num">{num(row.original.last)}</span> },
    { accessorKey: "change_pct", header: "涨跌", size: 84, cell: ({ row }) => <span className={`num ${changeTone(row.original.change_pct)}`}>{signedPct(row.original.change_pct / 100)}</span> },
    { accessorKey: "turnover", header: "换手", size: 78, cell: ({ row }) => <span className="num">{num(row.original.turnover)}%</span> },
    { accessorKey: "mktcap", header: "市值", size: 96, cell: ({ row }) => <span className="num" title={String(row.original.mktcap)}>{compact(row.original.mktcap)}</span> },
  ], []);

  const loading = overview.isLoading || securitiesQuery.isLoading;
  const fatalError = overview.error || securitiesQuery.error;
  const liveBadge = liveEnabled
    ? <Badge tone={tone === "live" ? "ok" : "neutral"} dot>{tone === "live" ? t.market.liveOn : liveSummary(liveStatus.data, null)}</Badge>
    : <Badge tone="warn" dot>{t.market.offlineSnapshot}</Badge>;
  const integrityBadgeTone = integrityTone(integrity.data?.status) === "ok" ? "ok" : integrityTone(integrity.data?.status) === "danger" ? "danger" : "warn";
  const snapshot = overview.data?.snapshot;
  const breadth = overview.data?.breadth;
  const breadthTotal = Math.max((breadth?.up ?? 0) + (breadth?.flat ?? 0) + (breadth?.down ?? 0), 1);
  const breadthWidth = (value: number | undefined) => `${(((value ?? 0) / breadthTotal) * 100).toFixed(2)}%`;

  return (
    <div className="page">
      <PageHeader
        title={t.market.title}
        subtitle={t.market.subtitle}
        actions={(
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={refresh} disabled={loading}>刷新</Button>
            <Button variant="primary" icon={SlidersHorizontal} href={`/backtest?code=${encodeURIComponent(code)}`}>开始一次研究</Button>
          </>
        )}
      />

      {fatalError && !overview.data && !rows.length ? (
        <StatePanel error={`${t.emptyStates.serviceOffline}：${fatalError.message}`} onRetry={refresh} />
      ) : null}
      {loading && !fatalError ? <Skeleton rows={6} /> : null}

      {overview.data ? (
        <div className="stack">
          <div className="grid grid-4">
            {views.map((view) => (
              <div className="index-card" key={view.key}>
                <div className="index-top">
                  <h3>{view.name}</h3>
                  <span className={changeTone(view.changePct)}>{signedPct(view.changePct == null ? null : view.changePct / 100)}</span>
                </div>
                <div className="kpi-value">{view.close == null ? "—" : num(view.close)}</div>
                <Sparkline values={view.spark.length ? view.spark : view.close != null ? [view.close, view.close] : []} positive={(view.changePct ?? 0) >= 0} height={28} />
                <small>{view.source === "live" ? t.appbar.live : view.source === "snapshot" ? t.common.snapshot : t.common.notAvailable}</small>
              </div>
            ))}
          </div>

          <div className="grid grid-2-1">
            <div className="stack">
              <Panel
                title={t.market.listTitle}
                subtitle={`${filtered.length} / ${rows.length} · ${listMode === "watch" ? t.market.listWatch : t.market.listAll}`}
                actions={(
                  <div className="row">
                    <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.market.searchPlaceholder} aria-label={t.market.searchPlaceholder} size="sm" style={{ width: 200 }} />
                    <Segmented ariaLabel="证券范围" size="sm" value={listMode} onChange={(value) => setListMode(value as "all" | "watch")} items={[{ value: "all", label: t.market.listAll }, { value: "watch", label: `${t.market.listWatch} ${codes.length}` }]} />
                  </div>
                )}
              >
                {listMode === "watch" && codes.length === 0 ? (
                  <StatePanel empty emptyHint={`${t.market.watchEmpty}：${t.market.watchEmptyHint}`} />
                ) : securitiesQuery.isError ? (
                  <StatePanel error={securitiesQuery.error.message} onRetry={() => void securitiesQuery.refetch()} />
                ) : (
                  <VirtualTable data={filtered} columns={columns} rowKey={(row) => row.sec_id} height={286} onRowClick={select} ariaLabel={t.market.listTitle} empty={<span className="text-3">{t.market.listEmpty}</span>} />
                )}
              </Panel>

              <Panel
                title={selected ? `${selected.code} ${selected.name}` : t.market.chart}
                subtitle={selected ? `${selected.board} · ${selected.industry}` : undefined}
                actions={(
                  <div className="chart-tools" aria-label={t.market.indicators}>
                    <button className={`chip ${showMA5 ? "active" : ""}`} onClick={() => setShowMA5((value) => !value)} aria-pressed={showMA5}>{t.market.ma5}</button>
                    <button className={`chip ${showMA20 ? "active" : ""}`} onClick={() => setShowMA20((value) => !value)} aria-pressed={showMA20}>{t.market.ma20}</button>
                    <button className={`chip ${showVolume ? "active" : ""}`} onClick={() => setShowVolume((value) => !value)} aria-pressed={showVolume}>{t.market.volumeLabel}</button>
                    <button className={`chip ${minuteMode ? "active" : ""}`} onClick={() => setMinuteMode((value) => !value)} aria-pressed={minuteMode}>{t.market.minute}</button>
                  </div>
                )}
              >
                {!minuteMode && (bars.isLoading ? <StatePanel loading /> : bars.error ? <StatePanel error={bars.error.message} onRetry={() => void bars.refetch()} /> : bars.data ? (
                  <KLineChart bars={bars.data} palette={palette} height={420} showMA5={showMA5} showMA20={showMA20} showVolume={showVolume} />
                ) : <StatePanel empty emptyHint={t.market.chartEmpty} />)}
                {minuteMode ? (
                  <div className="minute-panel" data-testid="minute-panel">
                    <div className="row-between" style={{ marginBottom: "var(--sp-4)" }}><span className="switch-title">{t.market.minutesTitle}</span><span className="page-note-sm">{t.market.minutesHint}</span></div>
                    {minuteBars.isLoading ? <StatePanel loading /> : minuteBars.error ? <StatePanel error={minuteBars.error.message} onRetry={() => void minuteBars.refetch()} /> : minuteBars.data ? (
                      <div className="table-wrap" style={{ maxHeight: 260 }}>
                        <table>
                          <thead><tr><th>时间</th><th className="num">开</th><th className="num">高</th><th className="num">低</th><th className="num">收</th><th className="num">量</th></tr></thead>
                          <tbody>
                            {minuteBars.data.bars.map((bar) => (
                              <tr key={bar.datetime}>
                                <td className="mono">{String(bar.datetime).slice(-4).replace(/(\d{2})(\d{2})/, "$1:$2")}</td>
                                <td className="num">{num(bar.open)}</td><td className="num">{num(bar.high)}</td>
                                <td className="num">{num(bar.low)}</td><td className="num">{num(bar.close)}</td>
                                <td className="num">{compact(bar.volume)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : <StatePanel empty emptyHint={t.market.minutesTitle} />}
                  </div>
                ) : null}
              </Panel>

              {profile.data ? (
                <Panel title={t.market.profile} dense>
                  <div className="profile-strip">
                    <div><span>{t.market.exchange}</span><strong>{profile.data.exchange || "—"}</strong></div>
                    <div><span>{t.market.board}</span><strong>{profile.data.board} · {profile.data.sec_type}</strong></div>
                    <div><span>{t.market.industry}</span><strong>{profile.data.industry || "—"}</strong></div>
                    <div><span>{t.market.listDate}</span><strong>{profile.data.list_date ? dateInt(profile.data.list_date) : "—"}</strong></div>
                    <div><span>{t.market.source}</span><strong>{profile.data.source || "—"}</strong></div>
                    <div><span>{t.market.lastAmount}</span><strong>{compact(profile.data.quote.amount)}</strong></div>
                  </div>
                </Panel>
              ) : null}

              {financials.data?.latest ? (
                <Panel title={`${t.market.financial} · 最近公告 ${String(financials.data.latest.ann_date)}`} subtitle={financials.data.note} dense>
                  <div className="table-wrap" style={{ maxHeight: 180 }}>
                    <table>
                      <thead><tr><th>报告期</th><th>公告日</th><th className="num">ROE</th><th className="num">EPS</th><th className="num">营收</th><th className="num">净利润</th></tr></thead>
                      <tbody>
                        {financials.data.rows.slice(0, 6).map((row) => (
                          <tr key={`${row.end_date}-${row.ann_date}`}>
                            <td className="mono">{String(row.end_date)}</td>
                            <td className="mono">{String(row.ann_date)}</td>
                            <td className="num">{row.roe == null ? "—" : `${(row.roe * 100).toFixed(2)}%`}</td>
                            <td className="num">{row.eps?.toFixed(2) ?? "—"}</td>
                            <td className="num">{row.revenue == null ? "—" : compact(row.revenue)}</td>
                            <td className="num">{row.net_profit == null ? "—" : compact(row.net_profit)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              ) : null}
            </div>

            <div className="stack">
              <Panel
                title={<><span className={DOT_CLASS[tone] ?? "dot"} aria-hidden="true" />{t.market.readings}</>}
                subtitle={liveSummary(liveStatus.data, snapshot?.end ? String(snapshot.end) : null)}
                actions={liveBadge}
              >
                <div className="readings-price">
                  <div className={`readings-price-value ${changeTone(readings.changePct)}`} key={readings.price ?? "none"}>{readings.price == null ? "—" : num(readings.price)}</div>
                  <div className={`readings-price-delta ${changeTone(readings.changePct)}`}>
                    {readings.change == null ? "—" : `${readings.change >= 0 ? "+" : ""}${num(readings.change)}`}{" · "}{signedPct(readings.changePct == null ? null : readings.changePct / 100)}
                  </div>
                </div>
                <div className="readings-grid">
                  <div className="reading-item"><span>{t.market.open}</span><strong>{num(readings.open)}</strong></div>
                  <div className="reading-item"><span>{t.market.high}</span><strong className="up">{num(readings.high)}</strong></div>
                  <div className="reading-item"><span>{t.market.low}</span><strong className="down">{num(readings.low)}</strong></div>
                  <div className="reading-item"><span>{t.market.preClose}</span><strong>{num(readings.preClose)}</strong></div>
                  <div className="reading-item"><span>{t.market.amount}</span><strong>{readings.amount == null ? "—" : compact(readings.amount)}</strong></div>
                  <div className="reading-item"><span>{t.market.amplitude}</span><strong>{readings.amplitudePct == null ? "—" : `${readings.amplitudePct.toFixed(2)}%`}</strong></div>
                  <div className="reading-item"><span>{t.market.limitUp}</span><strong className="up">{num(readings.limitUp)}</strong></div>
                  <div className="reading-item"><span>{t.market.limitDown}</span><strong className="down">{num(readings.limitDown)}</strong></div>
                  <div className="reading-item"><span>{t.market.turnover}</span><strong>{readings.turnoverPct == null ? "—" : `${num(readings.turnoverPct)}%`}</strong></div>
                  <div className="reading-item"><span>{t.market.updatedAt}</span><strong>{updatedAtLabel(readings)}</strong></div>
                </div>
                {!liveEnabled ? <p className="page-note-sm" style={{ marginTop: "var(--sp-4)" }}>{t.market.liveOff} <Link to="/settings">{t.common.openSettings}</Link></p> : null}
                {liveEnabled && liveQuotes.isError ? <p className="warn-text" style={{ marginTop: "var(--sp-4)" }}>{t.market.quoteFailed}</p> : null}
                {readings.suspended ? <p className="warn-text" style={{ marginTop: "var(--sp-4)" }}>{t.market.suspendedLabel}</p> : null}
                <div className="row" style={{ marginTop: "var(--sp-6)" }}>
                  <Button variant="secondary" icon={inWatchlist ? StarOff : Star} onClick={toggleWatch} disabled={!code} loading={saveWatchlist.isPending}>{inWatchlist ? t.market.removeWatch : t.market.addWatch}</Button>
                  <Button variant="primary" iconRight={ArrowRight} href={`/backtest?code=${encodeURIComponent(code)}`}>{t.home.cta}</Button>
                </div>
              </Panel>

              <Panel title={t.market.breadthTitle} subtitle={overview.data.as_of ? `${t.market.asOf} ${overview.data.as_of}` : undefined} dense>
                <div className="breadth">
                  <span className="up">上涨 {overview.data.breadth.up}</span>
                  <span className="down">下跌 {overview.data.breadth.down}</span>
                  <span>平盘 {overview.data.breadth.flat}</span>
                  <span>涨停 {overview.data.breadth.limit_up}</span>
                  <span>跌停 {overview.data.breadth.limit_down}</span>
                  <span>{t.market.suspendedLabel} {overview.data.breadth.suspended}</span>
                </div>
                <div className="breadth-bar" aria-hidden="true" title={`上涨 ${overview.data.breadth.up} / 平盘 ${overview.data.breadth.flat} / 下跌 ${overview.data.breadth.down}`}>
                  <i className="up-bg" style={{ width: breadthWidth(overview.data.breadth.up) }} />
                  <i className="flat-bg" style={{ width: breadthWidth(overview.data.breadth.flat) }} />
                  <i className="down-bg" style={{ width: breadthWidth(overview.data.breadth.down) }} />
                </div>
              </Panel>

              <Panel
                title={<><ShieldCheck size={16} aria-hidden="true" />{t.market.integrity}</>}
                subtitle={snapshot ? `${t.market.snapshot} ${snapshot.id ?? "—"} · ${dateInt(snapshot.end)}` : t.market.snapshotDate}
                actions={<Button variant="ghost" size="sm" iconRight={ArrowRight} href="/data">{t.nav.data}</Button>}
              >
                <div className="stack-tight">
                  <div className="row">
                    <Badge tone={integrityBadgeTone} dot>{integrityLabel(integrity.data?.status)}</Badge>
                    <Badge tone={snapshot?.synthetic ? "warn" : "neutral"}>{snapshot?.synthetic ? "SYNTHETIC" : snapshot?.source && snapshot.source !== "unknown" ? snapshot.source : t.common.snapshot}</Badge>
                  </div>
                  {integrity.data ? (
                    <>
                      <div className="row">
                        <span className="page-note-sm">{t.integrity.coverage}</span>
                        <strong>{num(integrity.data.coverage.coverage_pct)}%</strong>
                        <span className="page-note-sm">· {t.integrity.gaps} {compact(integrity.data.gaps.missing_days)}</span>
                        <span className="page-note-sm">· {integrity.data.gaps.symbols_with_gaps} {t.market.symbolsWithGaps}</span>
                      </div>
                      {(integrity.data.checks ?? []).filter((check) => check.status !== "pass").slice(0, 3).map((check) => (
                        <p key={check.id} className={check.status === "fail" ? "error-text" : "warn-text"}>{check.title}：{check.detail}</p>
                      ))}
                    </>
                  ) : <p className="page-note-sm">{integrity.isError ? integrity.error.message : t.integrity.notRun}</p>}
                </div>
              </Panel>
            </div>
          </div>

          {snapshot?.synthetic ? <p className="page-note-sm">{t.market.synthetic}</p> : null}
        </div>
      ) : null}
      <p className="page-note-sm">{t.disclaimer}</p>
    </div>
  );
}
