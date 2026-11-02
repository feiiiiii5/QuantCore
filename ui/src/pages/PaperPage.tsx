import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Pause, Play, Plus, RefreshCw, SkipForward, Square, Trash2, Wallet } from "lucide-react";
import { api, getApiBase, getToken } from "../api/client";
import type { PaperOrder, PaperSessionDetail, PaperSessionSummary, SecurityRow, SnapshotStatus } from "../api/types";
import { Badge, Chart, ChartCard, EmptyState, Panel, StatTile, Tabs } from "../components";
import PaperPortfolioPanel from "../components/PaperPortfolioPanel";
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
  const [code, setCode] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("100");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [autoRunning, setAutoRunning] = useState(false);
  const [alerts, setAlerts] = useState<Array<{ id: string; type: "equity_above" | "equity_below"; value: number }>>([]);
  const [alertType, setAlertType] = useState<"equity_above" | "equity_below">("equity_below");
  const [alertValue, setAlertValue] = useState("");
  const playTimer = useRef<number | null>(null);

  const stopPlay = useCallback(() => {
    if (playTimer.current !== null) {
      window.clearInterval(playTimer.current);
      playTimer.current = null;
    }
    setPlaying(false);
  }, []);
  useEffect(() => stopPlay, [stopPlay]);

  const loadSessions = useCallback(async () => {
    try {
      const list = await api.paperSessions();
      setSessions(list);
      if (!selected && list.length) setSelected(list[0].id);
    } catch (e) {
      setError(`${e}`);
    }
  }, [selected]);
  const loadDetail = useCallback(async (sessionId: string) => {
    if (!sessionId) return;
    try {
      setDetail(await api.paperSession(sessionId));
      setError("");
    } catch (e) { setError(`${e}`); }
  }, []);
  useEffect(() => {
    void loadSessions();
    api.snapshots().then(setSnapshots).catch(() => setSnapshots([]));
    api.securities("", 300).then(setSecurities).catch(() => setSecurities([]));
  }, [loadSessions]);
  useEffect(() => { if (selected) void loadDetail(selected); }, [selected, loadDetail]);
  useEffect(() => {
    if (!autoRunning || !selected) return;
    const timer = window.setInterval(() => {
      api.paperSession(selected).then((next) => { setDetail(next); checkAlerts(next); }).catch(() => undefined);
      api.paperAutoStatus(selected).then((status) => { if (!status.running) setAutoRunning(false); }).catch(() => undefined);
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
      const created = await api.createPaperSession({ snapshot: snapshot || null, initial_cash: Number(cash), name: name || undefined });
      setSelected(created.id);
      await loadSessions();
      await loadDetail(created.id);
      setName("");
    } catch (e) { setError(`${e}`); } finally { setBusy(false); }
  };
  const step = async () => {
    if (!selected) return;
    try {
      const next = await api.stepPaper(selected, 1);
      setDetail(next);
      checkAlerts(next);
      const fills = next.fills?.length ?? 0;
      if (fills > 0) notify({ title: "模拟成交", body: `${fills} 笔委托在 ${dateText(next.session.current_date)} 成交（仅本地模拟）`, kind: "success" });
      await loadSessions();
    } catch (e) { stopPlay(); setError(`${e}`); }
  };
  const toggleAuto = async () => {
    if (!selected) return;
    try {
      if (autoRunning) { await api.stopPaperAuto(selected); setAutoRunning(false); notify({ title: "持续模拟已停止", kind: "info" }); }
      else {
        const status = await api.startPaperAuto(selected, 1000);
        setAutoRunning(status.running);
        notify({ title: "持续模拟已启动", body: "服务端模拟时钟每 1s 推进 1 个交易日（历史快照，非实时行情）", kind: "info" });
      }
      await loadSessions();
    } catch (e) { setError(`${e}`); }
  };
  const togglePlay = () => {
    if (playing) { stopPlay(); return; }
    setPlaying(true);
    playTimer.current = window.setInterval(() => { void step(); }, 900);
  };
  const reset = async () => {
    if (!selected) return;
    try { setDetail(await api.resetPaper(selected)); await loadSessions(); }
    catch (e) { setError(`${e}`); }
  };
  const remove = async () => {
    if (!selected || !window.confirm("删除这个模拟会话？仅删除本地模拟记录。")) return;
    try { await api.deletePaperSession(selected); setSelected(""); setDetail(null); await loadSessions(); }
    catch (e) { setError(`${e}`); }
  };
  const submitOrder = async () => {
    if (!selected) return;
    setError("");
    try {
      const payload: Record<string, unknown> = { code: code.trim(), side, qty: Number(qty), order_type: orderType };
      if (orderType === "limit") payload.limit_price = Number(limitPrice);
      await api.submitPaperOrder(selected, payload);
      setDetail(await api.paperSession(selected));
      await loadSessions();
    } catch (e) { setError(`${e}`); }
  };
  const cancelOrder = async (order: PaperOrder) => {
    if (!selected) return;
    try { await api.cancelPaperOrder(selected, order.id); setDetail(await api.paperSession(selected)); }
    catch (e) { setError(`${e}`); }
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
  const equityOption = useMemo(() => {
    if (!detail?.equity_curve.length) return null;
    return {
      animation: false,
      tooltip: { trigger: "axis" as const },
      grid: { left: 70, right: 20, top: 20, bottom: 30 },
      xAxis: { type: "category" as const, data: detail.equity_curve.map((point) => dateText(point.date)), axisLabel: { fontSize: 10 } },
      yAxis: { type: "value" as const, scale: true, splitLine: { lineStyle: { color: "var(--border)" } } },
      series: [{ type: "line" as const, data: detail.equity_curve.map((point) => point.equity), showSymbol: false, lineStyle: { width: 1.8, color: "var(--primary)" }, areaStyle: { opacity: 0.08 } }],
    };
  }, [detail]);
  const filteredSecurities = useMemo(() => {
    if (!code.trim()) return [];
    const text = code.trim().toLowerCase();
    return securities.filter((row) => `${row.code}${row.name}`.toLowerCase().includes(text)).slice(0, 6);
  }, [code, securities]);
  const pendingOrders = detail?.orders.filter((order) => order.status === "pending" || order.status === "partial").length ?? 0;
  const totalPnl = account?.pnl ?? 0;

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>模拟交易</h1><p className="page-lead">本地虚拟账户，历史快照逐日推进；不连接券商、不产生真实委托。</p></div>
        <div className="page-head-actions">
          <button className="btn ghost" onClick={() => void downloadSignals()} disabled={!selected}><Download size={15} /> 信号 CSV</button>
          <button className="btn primary" onClick={() => void step()} disabled={!selected || playing}><SkipForward size={15} /> 下一交易日</button>
          <button className="btn" onClick={togglePlay} disabled={!selected}>{playing ? <Pause size={15} /> : <Play size={15} />} {playing ? "暂停" : "自动推进"}</button>
          <button className={`btn ${autoRunning ? "danger" : ""}`} onClick={() => void toggleAuto()} disabled={!selected}>{autoRunning ? <Square size={15} /> : <Play size={15} />} {autoRunning ? "停止持续模拟" : "持续模拟"}</button>
          <button className="btn" onClick={() => void reset()} disabled={!selected}><RefreshCw size={15} /> 重置</button>
          <button className="btn danger" onClick={() => void remove()} disabled={!selected}><Trash2 size={15} /> 删除</button>
        </div>
      </header>
      {error ? <p className="error" role="alert">{error}</p> : null}

      <div className="grid backtest-layout">
        <div className="stack">
          <Panel title="新建模拟会话" subtitle="快照决定用哪份历史数据；初始资金只影响虚拟账户">
            <label className="field-label">会话名称<input placeholder="会话名称（可选）" value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label className="field-label">快照<select value={snapshot} onChange={(event) => setSnapshot(event.target.value)}>
              <option value="">最新可用快照</option>
              {snapshots.map((item) => <option key={item.id || "s"} value={item.id || ""}>{item.id?.slice(0, 18) || "snapshot"} · {item.n_sec} 券</option>)}
            </select></label>
            <label className="field-label">初始资金（元）<input value={cash} onChange={(event) => setCash(event.target.value)} inputMode="decimal" /></label>
            <button className="btn primary" style={{ marginTop: 8 }} onClick={() => void createSession()} disabled={busy || !snapshots.length}><Plus size={15} /> 创建会话</button>
            {!snapshots.length ? <p className="muted small">还没有快照。先去「数据」页或首页「一键示例」构建 SYNTHETIC 快照。</p> : null}
          </Panel>
          <Panel title="模拟会话" subtitle={`${sessions.length} 个 · 权益 / 收益 / 持仓 / 待成交`}>
            {!sessions.length ? <EmptyState title="还没有模拟会话" hint="先创建会话，再逐日推进或提交模拟委托。" /> : (
              <div className="session-grid">
                {sessions.map((session) => {
                  const sessionPnl = session.equity - session.starting_cash;
                  return (
                    <button key={session.id} type="button" className={`session-card ${selected === session.id ? "active" : ""}`} onClick={() => setSelected(session.id)}>
                      <strong title={session.name}>{session.name}</strong>
                      <small>{session.id.slice(0, 14)} · {dateText(session.current_date)} · {session.status}</small>
                      <div className="session-stats">
                        <span>权益<b>{money(session.equity)}</b></span>
                        <span>收益<b className={sessionPnl >= 0 ? "up" : "down"}>{pct(session.starting_cash ? sessionPnl / session.starting_cash : 0)}</b></span>
                        <span>持仓<b>{session.position_count}</b></span>
                        <span>待成交<b>{session.pending_orders}</b></span>
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
                subtitle={`${dateText(detail.session.current_date)} / ${dateText(detail.session.end_date)} · 快照 ${detail.session.snapshot || "—"} · ${detail.session.synthetic ? "SYNTHETIC" : "本地数据"}`}
                actions={autoRunning ? <Badge tone="ok" dot>持续模拟中</Badge> : <Badge tone="neutral">{detail.session.status}</Badge>}
              >
                <div className="stat-grid">
                  <StatTile label="总权益" value={money(account?.equity ?? 0)} trend={totalPnl >= 0 ? "up" : "down"} tone={totalPnl >= 0 ? "up" : "down"} hint={`初始 ${money(detail.session.starting_cash)}`} />
                  <StatTile label="收益" value={`${money(account?.pnl ?? 0)}（${pct(account?.pnl_pct ?? 0)}）`} tone={totalPnl >= 0 ? "up" : "down"} hint="含费用，仅虚拟账户" />
                  <StatTile label="持仓市值" value={money(account?.market_value ?? 0)} hint={`现金 ${money(account?.cash ?? 0)}`} />
                  <StatTile label="待成交" value={pendingOrders} hint={`委托 ${detail.orders.length} · 成交 ${detail.trades.length}`} />
                </div>
                <ChartCard title="权益曲线" subtitle="历史快照回放，非实时行情" height={240}>{equityOption ? <Chart option={equityOption} height={240} /> : <EmptyState compact title="还没有权益曲线" hint="推进一个交易日后显示。" />}</ChartCard>
              </Panel>

              <Panel title="账户明细" subtitle="持仓 / 委托 / 成交；部分成交会显示 成交/委托 数量">
                <Tabs items={TAB_ITEMS.map((item) => item.id === "orders" ? { ...item, badge: pendingOrders || undefined } : item)} value={tab} onChange={setTab} ariaLabel="模拟账户明细" />
                {tab === "positions" ? (
                  <div className="table-wrap"><table><thead><tr><th>代码</th><th>名称</th><th className="num">数量</th><th className="num">可卖</th><th className="num">成本</th><th className="num">现价</th><th className="num">盈亏</th></tr></thead>
                    <tbody>{detail.positions.map((pos) => <tr key={pos.sec_id}><td className="mono">{pos.code}</td><td>{pos.name}</td><td className="num">{pos.qty}</td><td className="num">{pos.available}</td><td className="num">{pos.avg_cost.toFixed(2)}</td><td className="num">{pos.last.toFixed(2)}</td><td className={`num ${pos.pnl >= 0 ? "up" : "down"}`}>{money(pos.pnl)}</td></tr>)}</tbody></table>
                    {!detail.positions.length ? <EmptyState compact title="暂无持仓" hint="提交买入委托并推进交易日后显示。" /> : null}
                  </div>
                ) : null}
                {tab === "orders" ? (
                  <div className="table-wrap"><table><thead><tr><th>日期</th><th>代码</th><th>方向</th><th className="num">成交/委托</th><th>类型</th><th>状态</th><th className="num">成交价</th><th></th></tr></thead>
                    <tbody>{detail.orders.slice().reverse().slice(0, 30).map((order) => {
                      const status = ORDER_STATUS[order.status] ?? { text: order.status, tone: "neutral" as const };
                      return <tr key={order.id}><td>{dateText(order.date)}</td><td className="mono">{order.code}</td><td className={order.side === "buy" ? "up" : "down"}>{order.side === "buy" ? "买入" : "卖出"}</td><td className="num">{order.filled_qty > 0 && order.filled_qty < order.qty ? `${order.filled_qty}/${order.qty}` : order.qty}</td><td>{order.order_type === "market" ? "市价" : `限价 ${order.limit_price?.toFixed(2) ?? ""}`}</td><td><Badge tone={status.tone}>{status.text}</Badge>{order.reason ? <span className="muted small"> {order.reason}</span> : null}</td><td className="num">{order.fill_price?.toFixed(2) ?? "—"}</td><td>{(order.status === "pending" || order.status === "partial") ? <button className="btn ghost" onClick={() => void cancelOrder(order)}><Square size={13} /> 撤单</button> : null}</td></tr>;
                    })}</tbody></table>
                    {!detail.orders.length ? <EmptyState compact title="暂无委托" hint="用下方下单面板提交第一笔模拟委托。" /> : null}
                  </div>
                ) : null}
                {tab === "trades" ? (
                  <div className="table-wrap"><table><thead><tr><th>日期</th><th>代码</th><th>方向</th><th className="num">数量</th><th className="num">价格</th><th className="num">金额</th><th className="num">费用</th></tr></thead>
                    <tbody>{detail.trades.slice().reverse().slice(0, 30).map((trade) => <tr key={trade.id}><td>{dateText(trade.date)}</td><td className="mono">{trade.code}</td><td className={trade.side === "buy" ? "up" : "down"}>{trade.side === "buy" ? "买入" : "卖出"}</td><td className="num">{trade.qty}</td><td className="num">{trade.price.toFixed(2)}</td><td className="num">{money(trade.amount)}</td><td className="num">{money(trade.fee_total)}</td></tr>)}</tbody></table>
                    {!detail.trades.length ? <EmptyState compact title="暂无成交" hint="委托撮合后在这里显示逐笔成交。" /> : null}
                  </div>
                ) : null}
              </Panel>

              <Panel title="提交模拟委托" subtitle="市价委托在下一交易日开盘撮合；限价委托在价格触及时撮合">
                <div className="form-grid">
                  <label>代码<input value={code} onChange={(event) => setCode(event.target.value)} list="paper-codes" placeholder="600000" /></label>
                  <label>方向<select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")}><option value="buy">买入</option><option value="sell">卖出</option></select></label>
                  <label>数量<input value={qty} onChange={(event) => setQty(event.target.value)} inputMode="numeric" /></label>
                  <label>类型<select value={orderType} onChange={(event) => setOrderType(event.target.value as "market" | "limit")}><option value="market">市价（次日开盘）</option><option value="limit">限价</option></select></label>
                  {orderType === "limit" ? <label>限价<input value={limitPrice} onChange={(event) => setLimitPrice(event.target.value)} inputMode="decimal" /></label> : null}
                </div>
                <datalist id="paper-codes">{filteredSecurities.map((row) => <option key={row.sec_id} value={row.code}>{row.name}</option>)}</datalist>
                <button className="btn primary" style={{ marginTop: 8 }} onClick={() => void submitOrder()} disabled={!code.trim() || !qty}><Plus size={15} /> 提交委托</button>
                <p className="muted small">新手提示：市价单会在下一交易日按开盘价撮合；A 股 T+1，当日买入次日才能卖。规则复用回测费用/手数/T+1/涨跌停，仅本地模拟。</p>
              </Panel>

              <Panel title="本地提醒" subtitle="仅本机 localStorage；每次推进交易日后检查" dense>
                <div className="row">
                  <select value={alertType} onChange={(event) => setAlertType(event.target.value as "equity_above" | "equity_below")} style={{ maxWidth: 140 }}><option value="equity_below">权益低于</option><option value="equity_above">权益高于</option></select>
                  <input placeholder="金额" value={alertValue} onChange={(event) => setAlertValue(event.target.value)} inputMode="decimal" style={{ maxWidth: 140 }} />
                  <button className="btn" onClick={() => { const value = Number(alertValue); if (!Number.isFinite(value) || value <= 0) return; saveAlerts([...alerts, { id: `alert_${Date.now()}`, type: alertType, value }]); setAlertValue(""); }}>添加提醒</button>
                </div>
                {alerts.length ? <div className="alert-list">{alerts.map((alert) => <span className="badge" key={alert.id}>{alert.type === "equity_below" ? "≤" : "≥"} {money(alert.value)} <button className="link-btn" onClick={() => saveAlerts(alerts.filter((item) => item.id !== alert.id))}>×</button></span>)}</div> : <p className="muted small">暂无提醒；例如「权益低于 900,000」会在下次推进后 toast/桌面通知。</p>}
              </Panel>
            </>
          )}
        </div>
      </div>
      <PaperPortfolioPanel sessions={sessions} />
      <p className="muted small">虚拟账户仅用于研究；历史快照回放不代表未来收益，不构成投资建议。{t.disclaimer}</p>
    </div>
  );
}
