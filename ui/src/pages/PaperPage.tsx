import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Pause, Play, Plus, RefreshCw, SkipForward, Square, Trash2, Wallet } from "lucide-react";
import { api, getApiBase, getToken } from "../api/client";
import type { PaperOrder, PaperSessionDetail, PaperSessionSummary, SecurityRow, SnapshotStatus } from "../api/types";
import {
  Badge, Button, Chart, ChartCard, EmptyState, Field, Input, PageHeader, Panel, Select,
  StatTile, Tabs, type ChartSeries,
} from "../components";
import PaperPortfolioPanel from "../components/PaperPortfolioPanel";
import PaperCorporateEvents from "../components/PaperCorporateEvents";
import { notify } from "../lib/notify";
import { dateInt, money, pct } from "../lib/format";
import { zhCN as t } from "../i18n/zh-CN";
import "./pages.css";

const ORDER_STATUS: Record<string, { text: string; tone: "neutral" | "info" | "warn" | "ok" | "danger" }> = {
  pending: { text: "待成交", tone: "info" },
  partial: { text: "部分成交", tone: "warn" },
  filled: { text: "已成交", tone: "ok" },
  cancelled: { text: "已撤销", tone: "neutral" },
  rejected: { text: "已拒绝", tone: "danger" },
};
const TAB_ITEMS = [{ id: "positions", label: "持仓" }, { id: "orders", label: "委托" }, { id: "trades", label: "成交" }];
const dateText = (value: number) => dateInt(value);

export default function PaperPage() {
  const [sessions, setSessions] = useState<PaperSessionSummary[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotStatus[]>([]);
  const [securities, setSecurities] = useState<SecurityRow[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [detail, setDetail] = useState<PaperSessionDetail | null>(null);
  const [tab, setTab] = useState("positions");
  const [name, setName] = useState("");
  const [cash, setCash] = useState("1000000");
  const [snapshot, setSnapshot] = useState("");
  const [mode, setMode] = useState<"historical" | "live">("historical");
  const [code, setCode] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("100");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stepping, setStepping] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [autoRunning, setAutoRunning] = useState(false);
  const [alerts, setAlerts] = useState<Array<{ id: string; type: "equity_above" | "equity_below"; value: number }>>([]);
  const [alertType, setAlertType] = useState<"equity_above" | "equity_below">("equity_below");
  const [alertValue, setAlertValue] = useState("");
  const playTimer = useRef<number | null>(null);
  const selectedRef = useRef("");
  const stepInFlight = useRef(false);
  const liveInFlight = useRef(false);

  const stopPlay = useCallback(() => {
    if (playTimer.current !== null) {
      window.clearInterval(playTimer.current);
      playTimer.current = null;
    }
    setPlaying(false);
  }, []);
  useEffect(() => stopPlay, [stopPlay]);
  const selectSession = useCallback((sessionId: string) => {
    if (selectedRef.current === sessionId) return;
    stopPlay();
    selectedRef.current = sessionId;
    setSelected(sessionId);
    setDetail(null);
    setAutoRunning(false);
    setError("");
  }, [stopPlay]);

  const loadSessions = useCallback(async () => {
    try {
      const list = await api.paperSessions();
      setSessions(list);
      if (!selectedRef.current && list.length) selectSession(list[0].id);
    } catch (e) { setError(`${e}`); }
  }, [selectSession]);
  const loadDetail = useCallback(async (sessionId: string) => {
    if (!sessionId) return;
    try {
      const next = await api.paperSession(sessionId);
      if (selectedRef.current !== sessionId) return;
      setDetail(next);
      setSessions((list) => list.map((item) => item.id === sessionId ? next.session : item));
      setError("");
    } catch (e) { if (selectedRef.current === sessionId) setError(`${e}`); }
  }, []);
  const refreshLive = useCallback(async (sessionId: string) => {
    if (!sessionId || liveInFlight.current) return;
    liveInFlight.current = true;
    try {
      const next = await api.refreshPaper(sessionId);
      if (selectedRef.current !== sessionId) return;
      setDetail(next);
      setSessions((list) => list.map((item) => item.id === sessionId ? next.session : item));
      setError("");
      if (next.fills?.length) notify({ title: "实时模拟成交", body: `${next.fills.length} 笔虚拟成交`, kind: "success" });
    } catch (e) { if (selectedRef.current === sessionId) setError(`${e}`); }
    finally { liveInFlight.current = false; }
  }, []);
  useEffect(() => {
    void loadSessions();
    api.snapshots().then(setSnapshots).catch(() => setSnapshots([]));
    api.securities("", 300).then(setSecurities).catch(() => setSecurities([]));
  }, [loadSessions]);
  useEffect(() => {
    if (!selected) return;
    void loadDetail(selected);
    api.paperAutoStatus(selected).then((status) => {
      if (selectedRef.current === selected) setAutoRunning(status.running);
    }).catch(() => undefined);
  }, [selected, loadDetail]);
  useEffect(() => {
    if (!selected || detail?.session.mode !== "live") return;
    void refreshLive(selected);
    const timer = window.setInterval(() => { void refreshLive(selected); }, 3000);
    return () => window.clearInterval(timer);
  }, [selected, detail?.session.mode, refreshLive]);
  useEffect(() => {
    if (!autoRunning || !selected) return;
    const timer = window.setInterval(() => {
      api.paperSession(selected).then((next) => { if (selectedRef.current === selected) { setDetail(next); checkAlerts(next); } }).catch(() => undefined);
      api.paperAutoStatus(selected).then((status) => { if (selectedRef.current === selected && !status.running) setAutoRunning(false); }).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRunning, selected]);

  const storageKey = selected ? `qc_paper_alerts_${selected}` : "";
  useEffect(() => {
    if (!storageKey) { setAlerts([]); return; }
    try {
      const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]") as Array<{ id: string; type: "equity_above" | "equity_below"; value: number }>;
      setAlerts(Array.isArray(parsed) ? parsed : []);
    } catch { setAlerts([]); }
  }, [storageKey]);
  const saveAlerts = (next: Array<{ id: string; type: "equity_above" | "equity_below"; value: number }>) => {
    setAlerts(next);
    if (storageKey) localStorage.setItem(storageKey, JSON.stringify(next));
  };
  const checkAlerts = (next: PaperSessionDetail) => {
    const equity = next.account.equity;
    for (const alert of alerts) {
      const hit = alert.type === "equity_below" ? equity <= alert.value : equity >= alert.value;
      if (hit) notify({ title: "模拟账户提醒", body: `权益 ${money(equity)} ${alert.type === "equity_below" ? "低于" : "高于"} ${money(alert.value)}`, kind: "info" });
    }
  };

  const createSession = async () => {
    setBusy(true); setError("");
    try {
      const created = await api.createPaperSession({ mode, snapshot: mode === "historical" ? snapshot || null : null, initial_cash: Number(cash), name: name || undefined });
      selectSession(created.id);
      await loadSessions();
      await loadDetail(created.id);
      setName("");
    } catch (e) { setError(`${e}`); } finally { setBusy(false); }
  };
  const step = async () => {
    if (!selected || selectedRef.current !== selected || stepInFlight.current) return;
    stepInFlight.current = true;
    setStepping(true);
    try {
      const next = await api.stepPaper(selected, 1);
      if (selectedRef.current !== selected) return;
      setDetail(next);
      checkAlerts(next);
      if (next.session.status === "finished") stopPlay();
      const fills = next.fills?.length ?? 0;
      if (fills > 0) notify({ title: "模拟成交", body: `${fills} 笔委托在 ${dateText(next.session.current_date)} 成交（仅本地模拟）`, kind: "success" });
      await loadSessions();
    } catch (e) { if (selectedRef.current === selected) { stopPlay(); setError(`${e}`); } }
    finally { stepInFlight.current = false; setStepping(false); }
  };
  const toggleAuto = async () => {
    if (!selected || playing || stepInFlight.current) return;
    try {
      if (autoRunning) { await api.stopPaperAuto(selected); if (selectedRef.current !== selected) return; setAutoRunning(false); notify({ title: "持续模拟已停止", kind: "info" }); }
      else {
        const status = await api.startPaperAuto(selected, 1000);
        if (selectedRef.current !== selected) return;
        setAutoRunning(status.running);
        notify({ title: "持续模拟已启动", body: "服务端模拟时钟每 1s 推进 1 个交易日（历史快照，非实时行情）", kind: "info" });
      }
      await loadSessions();
    } catch (e) { if (selectedRef.current === selected) setError(`${e}`); }
  };
  const togglePlay = () => {
    if (playing) { stopPlay(); return; }
    setPlaying(true);
    playTimer.current = window.setInterval(() => { void step(); }, 900);
  };
  const reset = async () => {
    if (!selected || stepInFlight.current || autoRunning) return;
    stopPlay();
    try { const next = await api.resetPaper(selected); if (selectedRef.current === selected) setDetail(next); await loadSessions(); }
    catch (e) { if (selectedRef.current === selected) setError(`${e}`); }
  };
  const remove = async () => {
    if (!selected || stepInFlight.current || autoRunning || !window.confirm("删除这个模拟会话？仅删除本地模拟记录。")) return;
    stopPlay();
    try { await api.deletePaperSession(selected); if (selectedRef.current === selected) selectSession(""); await loadSessions(); }
    catch (e) { if (selectedRef.current === selected) setError(`${e}`); }
  };
  const submitOrder = async () => {
    if (!selected) return;
    setError("");
    try {
      const payload: Record<string, unknown> = { code: code.trim(), side, qty: Number(qty), order_type: orderType };
      if (orderType === "limit") payload.limit_price = Number(limitPrice);
      await api.submitPaperOrder(selected, payload);
      await loadDetail(selected);
      await loadSessions();
    } catch (e) { if (selectedRef.current === selected) setError(`${e}`); }
  };
  const cancelOrder = async (order: PaperOrder) => {
    if (!selected) return;
    try { await api.cancelPaperOrder(selected, order.id); await loadDetail(selected); }
    catch (e) { if (selectedRef.current === selected) setError(`${e}`); }
  };
  const downloadSignals = async () => {
    if (!selected) return;
    const response = await fetch(`${getApiBase()}/api/paper/sessions/${selected}/signals.csv`, { headers: { Authorization: `Bearer ${getToken()}` } });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${selected}_signals.csv`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const account = detail?.account;
  const isLive = detail?.session.mode === "live";
  const equitySeries = useMemo<ChartSeries[]>(() => {
    if (!detail?.equity_curve || detail.equity_curve.length < 2) return [];
    return [{ kind: "area", title: "权益", data: detail.equity_curve.map((point) => ({ time: point.date, value: point.equity })) }];
  }, [detail]);
  const filteredSecurities = useMemo(() => {
    if (isLive || !code.trim()) return [];
    const text = code.trim().toLowerCase();
    return securities.filter((row) => `${row.code}${row.name}`.toLowerCase().includes(text)).slice(0, 6);
  }, [code, securities, isLive]);
  const pendingOrders = detail?.orders.filter((order) => order.status === "pending" || order.status === "partial").length ?? 0;
  const totalPnl = account?.pnl ?? 0;

  return (
    <div className="page">
      <PageHeader
        title="模拟交易"
        subtitle="选择历史回放或实时行情模拟；资金、委托和成交均留在本地虚拟账户。"
        actions={(
          <>
            <Button variant="ghost" icon={Download} onClick={() => void downloadSignals()} disabled={!selected}>信号 CSV</Button>
            {isLive ? <Button variant="primary" icon={RefreshCw} onClick={() => void refreshLive(selected)}>刷新实时账户</Button> : <>
              <Button variant="primary" icon={SkipForward} onClick={() => void step()} disabled={!selected || playing || stepping || autoRunning}>下一交易日</Button>
              <Button variant="secondary" icon={playing ? Pause : Play} onClick={togglePlay} disabled={!selected || autoRunning || (stepping && !playing)}>{playing ? "暂停" : "自动推进"}</Button>
              <Button variant={autoRunning ? "danger" : "secondary"} icon={autoRunning ? Square : Play} onClick={() => void toggleAuto()} disabled={!selected || playing || stepping}>{autoRunning ? "停止持续模拟" : "持续模拟"}</Button>
            </>}
            <Button variant="secondary" icon={RefreshCw} onClick={() => void reset()} disabled={!selected || stepping || autoRunning}>重置</Button>
            <Button variant="danger" icon={Trash2} onClick={() => void remove()} disabled={!selected || stepping || autoRunning}>删除</Button>
          </>
        )}
      />
      {error ? <p className="error-text" role="alert">{error}</p> : null}

      <div className="grid grid-1-2">
        <div className="stack">
          <Panel title="新建模拟会话" subtitle="历史模式使用快照；实时模式使用已开启的公开行情">
            <div className="stack">
              <Field label="行情模式"><Select aria-label="行情模式" value={mode} onChange={(event) => setMode(event.target.value as "historical" | "live")} options={[{ value: "historical", label: "历史快照回放" }, { value: "live", label: "实时行情模拟" }]} /></Field>
              <Field label="会话名称"><Input placeholder="会话名称（可选）" value={name} onChange={(event) => setName(event.target.value)} aria-label="会话名称" /></Field>
              {mode === "historical" ? <Field label="快照">
                <Select value={snapshot} onChange={(event) => setSnapshot(event.target.value)} options={[{ value: "", label: "最新可用快照" }, ...snapshots.map((item) => ({ value: item.id || "", label: `${item.id?.slice(0, 18) || "snapshot"} · ${item.n_sec} 券` }))]} />
              </Field> : <p className="page-note-sm">实时模拟无需历史快照。启用实时行情后，页面每 3 秒请求更新；休市、停牌、缺时间戳或陈旧报价均不会模拟成交。</p>}
              <Field label="初始资金（元）"><Input value={cash} onChange={(event) => setCash(event.target.value)} inputMode="decimal" aria-label="初始资金（元）" /></Field>
              <div><Button variant="primary" icon={Plus} onClick={() => void createSession()} disabled={busy || (mode === "historical" && !snapshots.length)}>创建会话</Button></div>
              {mode === "historical" && !snapshots.length ? <p className="page-note-sm">还没有快照。先去「数据」页或首页「一键示例」构建 SYNTHETIC 快照。</p> : null}
            </div>
          </Panel>
          <Panel title="模拟会话" subtitle={`${sessions.length} 个 · 权益 / 收益 / 持仓 / 待成交`}>
            {!sessions.length ? <EmptyState title="还没有模拟会话" hint="先创建会话，再逐日推进或提交模拟委托。" /> : (
              <div className="session-grid">
                {sessions.map((session) => {
                  const sessionPnl = session.equity - session.starting_cash;
                  return (
                    <button key={session.id} type="button" className={`session-card ${selected === session.id ? "selected" : ""}`} onClick={() => selectSession(session.id)} aria-pressed={selected === session.id}>
                      <span className="session-card-name" title={session.name}>{session.name}</span>
                      <span className="session-card-sub">{session.id.slice(0, 14)} · {dateText(session.current_date)} · {session.mode === "live" ? "实时模拟" : "历史回放"}</span>
                      <div className="session-stats">
                        <div className="session-stat"><span>权益</span><b>{money(session.equity)}</b></div>
                        <div className="session-stat"><span>收益</span><b className={sessionPnl > 0 ? "up" : sessionPnl < 0 ? "down" : "flat"}>{pct(session.starting_cash ? sessionPnl / session.starting_cash : 0)}</b></div>
                        <div className="session-stat"><span>持仓</span><b>{session.position_count}</b></div>
                        <div className="session-stat"><span>待成交</span><b>{session.pending_orders}</b></div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </Panel>
        </div>

        <div className="stack">
          {!detail ? <Panel><EmptyState title="选择一个模拟会话" hint="创建或选择左侧会话，推进交易日并提交模拟委托。" icon={Wallet} /></Panel> : (
            <>
              <Panel
                title={detail.session.name}
                subtitle={isLive ? `${dateText(detail.session.current_date)} · 实时行情驱动的本地虚拟账户` : `${dateText(detail.session.current_date)} / ${dateText(detail.session.end_date)} · 快照 ${detail.session.snapshot || "—"} · ${detail.session.synthetic ? "SYNTHETIC" : "本地数据"}`}
                actions={autoRunning ? <Badge tone="ok" dot>持续模拟中</Badge> : <Badge tone="neutral">{detail.session.status}</Badge>}
              >
                <div className="stack">
                  {isLive ? <div role="status"><p className="page-note-sm">{detail.live?.notice || "等待有效行情；首次刷新建立成交量基线。"}</p>{detail.live?.quotes.map((quote) => <p className="page-note-sm" key={quote.code}>{quote.code} · {quote.timestamp || "无行情时间"} · {quote.reason || "有效报价"}</p>)}</div> : null}
                  <div className="grid grid-2">
                    <StatTile label="总权益" value={money(account?.equity ?? 0)} trend={totalPnl > 0 ? "up" : totalPnl < 0 ? "down" : "flat"} tone={totalPnl > 0 ? "up" : totalPnl < 0 ? "down" : "neutral"} hint={`初始 ${money(detail.session.starting_cash)}`} />
                    <StatTile label="收益" value={`${money(account?.pnl ?? 0)}（${pct(account?.pnl_pct ?? 0)}）`} tone={totalPnl > 0 ? "up" : totalPnl < 0 ? "down" : "neutral"} hint="含费用，仅虚拟账户" />
                    <StatTile label="持仓市值" value={money(account?.market_value ?? 0)} hint={`现金 ${money(account?.cash ?? 0)}`} />
                    <StatTile label="待成交" value={pendingOrders} hint={`委托 ${detail.orders.length} · 成交 ${detail.trades.length}`} />
                  </div>
                  <ChartCard title="权益曲线" subtitle={isLive ? "每日权益随有效行情更新；陈旧时沿用最后有效估值" : "历史快照回放，非实时行情"} height={240}>
                    {equitySeries.length ? <Chart series={equitySeries} height={240} ariaLabel="模拟账户权益曲线" valueFormatter={(value) => value.toFixed(0)} /> : <EmptyState compact title="还没有权益曲线" hint="推进一个交易日后显示。" />}
                  </ChartCard>
                </div>
              </Panel>

              <PaperCorporateEvents events={detail.corporate_events ?? []} live={isLive} />

              <Panel title="账户明细" subtitle="持仓 / 委托 / 成交；部分成交会显示 成交/委托 数量">
                <Tabs items={TAB_ITEMS.map((item) => item.id === "orders" ? { ...item, badge: pendingOrders || undefined } : item)} value={tab} onChange={setTab} ariaLabel="模拟账户明细" />
                {tab === "positions" ? (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>代码</th><th>名称</th><th className="num">数量</th><th className="num">可卖</th><th className="num">成本</th><th className="num">现价</th><th className="num">盈亏</th></tr></thead>
                      <tbody>{detail.positions.map((pos) => <tr key={pos.sec_id}><td className="mono">{pos.code}</td><td>{pos.name}</td><td className="num">{pos.qty}</td><td className="num">{pos.available}</td><td className="num">{pos.avg_cost.toFixed(2)}</td><td className="num" title={pos.quote_timestamp || undefined}>{pos.last.toFixed(2)}{isLive ? <div className="page-note-sm">{pos.quote_timestamp || "待更新"}</div> : null}</td><td className={`num ${pos.pnl >= 0 ? "up" : "down"}`}>{money(pos.pnl)}</td></tr>)}</tbody>
                    </table>
                    {!detail.positions.length ? <EmptyState compact title="暂无持仓" hint="提交买入委托并推进交易日后显示。" /> : null}
                  </div>
                ) : null}
                {tab === "orders" ? (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>日期</th><th>代码</th><th>方向</th><th className="num">成交/委托</th><th>类型</th><th>状态</th><th className="num">成交价</th><th /></tr></thead>
                      <tbody>
                        {detail.orders.slice().reverse().slice(0, 30).map((order) => {
                          const status = ORDER_STATUS[order.status] ?? { text: order.status, tone: "neutral" as const };
                          return (
                            <tr key={order.id}>
                              <td>{dateText(order.date)}</td>
                              <td className="mono">{order.code}</td>
                              <td className={order.side === "buy" ? "up" : "down"}>{order.side === "buy" ? "买入" : "卖出"}</td>
                              <td className="num">{order.filled_qty > 0 && order.filled_qty < order.qty ? `${order.filled_qty}/${order.qty}` : order.qty}</td>
                              <td>{order.order_type === "market" ? "市价" : `限价 ${order.limit_price?.toFixed(2) ?? ""}`}</td>
                              <td><Badge tone={status.tone}>{status.text}</Badge>{order.reason ? <span className="page-note-sm"> {order.reason}</span> : null}</td>
                              <td className="num">{order.fill_price?.toFixed(2) ?? "—"}</td>
                              <td>{(order.status === "pending" || order.status === "partial") ? <Button variant="ghost" size="sm" icon={Square} onClick={() => void cancelOrder(order)}>撤单</Button> : null}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {!detail.orders.length ? <EmptyState compact title="暂无委托" hint="用下方下单面板提交第一笔模拟委托。" /> : null}
                  </div>
                ) : null}
                {tab === "trades" ? (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>日期</th><th>代码</th><th>方向</th><th className="num">数量</th><th className="num">价格</th><th className="num">金额</th><th className="num">费用</th></tr></thead>
                      <tbody>{detail.trades.slice().reverse().slice(0, 30).map((trade) => <tr key={trade.id}><td>{dateText(trade.date)}</td><td className="mono">{trade.code}</td><td className={trade.side === "buy" ? "up" : "down"}>{trade.side === "buy" ? "买入" : "卖出"}</td><td className="num">{trade.qty}</td><td className="num">{trade.price.toFixed(2)}</td><td className="num">{money(trade.amount)}</td><td className="num">{money(trade.fee_total)}</td></tr>)}</tbody>
                    </table>
                    {!detail.trades.length ? <EmptyState compact title="暂无成交" hint="委托撮合后在这里显示逐笔成交。" /> : null}
                  </div>
                ) : null}
              </Panel>

              <Panel title="提交模拟委托" subtitle={isLive ? "以委托之后的新鲜报价模拟撮合，新增成交量限制可成交数量" : "市价委托在下一交易日开盘撮合；限价委托在价格触及时撮合"}>
                <div className="stack">
                  <div className="grid grid-3">
                    <Field label="代码"><Input value={code} onChange={(event) => setCode(event.target.value)} list="paper-codes" placeholder="600000" aria-label="代码" /></Field>
                    <Field label="方向"><Select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")} options={[{ value: "buy", label: "买入" }, { value: "sell", label: "卖出" }]} /></Field>
                    <Field label="数量"><Input value={qty} onChange={(event) => setQty(event.target.value)} inputMode="numeric" aria-label="数量" /></Field>
                    <Field label="类型"><Select value={orderType} onChange={(event) => setOrderType(event.target.value as "market" | "limit")} options={[{ value: "market", label: isLive ? "市价（后续有效行情）" : "市价（次日开盘）" }, { value: "limit", label: "限价" }]} /></Field>
                    {orderType === "limit" ? <Field label="限价"><Input value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} inputMode="decimal" aria-label="限价" /></Field> : null}
                  </div>
                  <datalist id="paper-codes">{filteredSecurities.map((row) => <option key={row.sec_id} value={row.code}>{row.name}</option>)}</datalist>
                  <div><Button variant="primary" icon={Plus} onClick={() => void submitOrder()} disabled={!code.trim() || !qty}>提交委托</Button></div>
                  <p className="page-note-sm">{isLive ? "首次报价只建立基线；后续新增成交量的 10% 用作虚拟撮合上限，限价只看下单后的最新价格。A 股 T+1，不模拟盘口排队、公司行为或真实成交保证。" : "新手提示：市价单会在下一交易日按开盘价撮合；A 股 T+1，当日买入次日才能卖。规则复用回测费用/手数/T+1/涨跌停，仅本地模拟。"}</p>
                </div>
              </Panel>

              <Panel title="本地提醒" subtitle="仅本机 localStorage；每次推进交易日后检查" dense>
                <div className="stack">
                  <div className="row">
                    <Select value={alertType} onChange={(event) => setAlertType(event.target.value as "equity_above" | "equity_below")} options={[{ value: "equity_below", label: "权益低于" }, { value: "equity_above", label: "权益高于" }]} style={{ maxWidth: 140 }} />
                    <Input placeholder="金额" value={alertValue} onChange={(event) => setAlertValue(event.target.value)} inputMode="decimal" style={{ maxWidth: 160 }} />
                    <Button variant="secondary" onClick={() => { const value = Number(alertValue); if (!Number.isFinite(value) || value <= 0) return; saveAlerts([...alerts, { id: `alert_${Date.now()}`, type: alertType, value }]); setAlertValue(""); }}>添加提醒</Button>
                  </div>
                  {alerts.length ? <div className="row">{alerts.map((alert) => <Badge key={alert.id} tone="neutral">{alert.type === "equity_below" ? "≤" : "≥"} {money(alert.value)} <button type="button" className="alert-remove" aria-label="移除提醒" onClick={() => saveAlerts(alerts.filter((item) => item.id !== alert.id))}>×</button></Badge>)}</div> : <p className="page-note-sm">暂无提醒；例如「权益低于 900,000」会在下次推进后 toast/桌面通知。</p>}
                </div>
              </Panel>
            </>
          )}
        </div>
      </div>
      <PaperPortfolioPanel sessions={sessions} />
      <p className="page-note-sm">虚拟账户仅用于研究；历史快照回放不代表未来收益，不构成投资建议。{t.disclaimer}</p>
    </div>
  );
}
