# UI ⇄ API contract v2 (local research workbench)

The server binds only to loopback. `/api/*` routes require `Authorization: Bearer <token>`; `/health` is public.
The built UI is served by `qc serve` from the same origin; CORS is disabled by default. An optional private Sites frontend
uses explicit, repeatable `qc serve --allow-origin https://exact-origin` entries. Only these HTTPS origins receive CORS and
Private Network Access preflight support; Host, Origin, Bearer and WebSocket checks remain enforced. This does not host the
C++/Python backend in Sites. See [Sites setup](SITES.md) for browser permissions and connection checks. For Vite dev,
`vite.config.ts` proxies `/api`, `/ws`, `/health` to `http://127.0.0.1:8000`.

WebSocket: `ws://127.0.0.1:<port>/ws/jobs/<job_id>?token=<token>` (jobs) and `/ws/live?token=<token>&codes=…` (live quotes); server validates Origin/Host/token.

## Meta / health
- `GET /health` → `{status,version,engine_backend,engine_available,panel_available,synthetic_only,cors}`
- `GET /api/meta` → `{version,engine_backend,synthetic_only,data_root,snapshots_root,experiments_root,token_required,ui_served}`

## Local self-check (doctor)
- `GET /api/doctor?include_optional=true` →
  `{status:"ok"|"warn"|"fail",generated_at,version,engine_backend,engine_available,panel_available,root,counts:{pass,warn,fail,skip},checks:[{id,title,status:"pass"|"warn"|"fail"|"skip",detail,hint,required}]}`
- Read-only local environment check (Python/deps, C++ engine/panel, data roots); it never touches the network and never mutates files. `include_optional=false` skips optional checks; `hint` is a short fix-it string (empty when there is nothing to do).
- `root` is the server process `Path.cwd()`; `data_root`/`snapshots_root` come from the server workspace settings (not from query parameters). The loopback port probe is disabled here (the server already owns its port); `qc doctor` on the CLI still probes it.
- Request: `curl -H "Authorization: Bearer <token>" "http://127.0.0.1:8000/api/doctor?include_optional=true"`.
- Errors: 401 `{detail:"missing or invalid bearer token"}` without a valid token; 500 `{detail:"internal server error"}` only if the check itself crashes (not expected).
- UI: 设置页「本地自检」卡片 — the check runs only when the user clicks 运行自检 (no polling, no auto-run).

```json
{
  "status": "warn",
  "generated_at": "2026-01-02T03:04:05+08:00",
  "version": "0.1.0",
  "engine_backend": "cpp",
  "engine_available": true,
  "panel_available": true,
  "root": "<workspace>",
  "counts": {"pass": 10, "warn": 2, "fail": 0, "skip": 2},
  "checks": [
    {"id": "python", "title": "Python runtime", "status": "pass", "detail": "Python 3.12.x (...); project .venv", "hint": "", "required": true},
    {"id": "snapshots", "title": "Snapshots", "status": "warn", "detail": "no snapshots under data/snapshots", "hint": "uv run qc snapshot build", "required": false}
  ]
}
```

## Market
- `GET /api/market/overview?snapshot=<id|prefix>` →
  `{snapshot:{id,content_hash,n_sec,n_time,start,end,synthetic,source,fields[]}, indices:[{name,close,change_pct,spark[]}], breadth:{up,down,flat,limit_up,limit_down,suspended}, sectors:[{name,count,avg_change,up,down}], updated_at}`
- `GET /api/market/bars?snapshot=&code=&start=&end=&limit=600` →
  `{code,name,board,dates[],open[],high[],low[],close[],volume[],amount[],turnover[],ma5[],ma20[],limit_up[],limit_down[],suspended[]}`
- `GET /api/market/securities?snapshot=&query=&codes=&limit=200` (limit ≤1000; codes is an exact comma-separated code filter; query is literal, case-insensitive text over code/name/sec_id/industry/board) →
  `[{sec_id,code,name,board,industry,last,change_pct,turnover,mktcap,float_mktcap,suspended,st}]`

## Live market quotes (read-only, network opt-in)
- Live quotes poll a public quote source only when the server is started with `QC_ALLOW_NETWORK=1`; the default is fully offline and the endpoints still answer with an explicit `off` state. These routes do not submit orders or mutate research data. The separate live paper API can consume the cached quotes for virtual fills; there is no broker. Sources: Eastmoney (primary, `push2` batch JSON) with Sina (`hq.sinajs.cn`) fallback; `QC_LIVE_INTERVAL` sets the poll interval (2–30s, default 3s).
- `GET /api/live/status` →
  `{enabled,source:"eastmoney"|"sina"|"none",state:"off"|"idle"|"connecting"|"live"|"error"|"closed",market:{phase:"pre_open"|"open"|"lunch"|"closed"|"holiday",label,is_trading_day,server_time,next_open,last_trade_date},as_of,latency_ms,subscribed,error,notice}`
- `GET /api/live/indices` → `{as_of,source,stale,quotes:[…]}` for 上证指数/深证成指/创业板指/科创50 (codes 000001/399001/399006/000688).
- `GET /api/live/quotes?codes=600000,000001` → same envelope; `codes` is 6-digit A-share codes (max 50, deduped); empty `codes` falls back to the persisted watchlist. Invalid code → 400.
- Quote shape: `{code,name,price,prev_close,open,high,low,change,change_pct,volume,amount,turnover_pct,limit_up,limit_down,suspended,timestamp,source,stale}`. `volume` is shares for stocks (Eastmoney lots ×100) and the index aggregate is display-only; closed/suspended rows fall back to the previous close with `suspended=true`.
- Quote `timestamp` is the source time, never the fetch time. Missing, invalid or old source times mark the individual row stale; an aggregate live status does not certify every row. Stock/index groups and omitted or stale symbols have independent fallback, so a response can mix sources.
- `GET /api/live/bars?code=600000&limit=600` (10–2000) → the market-bars OHLCV/MA shape plus `{synthetic:false,source,as_of,note}`. No snapshot is needed. Eastmoney raw daily bars fall back to Sina; unsupported amount/turnover are null. `as_of` is fetch/cache time, not a guaranteed trade timestamp. Bounded in-memory cache: 32 keys, 60s during pre-open/open/lunch, otherwise 300s. Data is display-only and never writes snapshots/warehouse. Network disabled → 409; both sources fail → 503; invalid code → 400. The UI searches codes directly and merges only valid fresh quotes into the current candle.
- `GET /api/watchlist` / `PUT /api/watchlist` `{codes:[…]}` (see onboarding section) is the server-side subscription list for the poller.
- **WebSocket** `ws://127.0.0.1:<port>/ws/live?token=<token>&codes=600000,000001` pushes `{type:"snapshot",status,indices,quotes}` every poll interval; same Host/Origin/token checks as `/ws/jobs`.
- The UI shows a green 实时 dot with the last update time, or an explicit 离线/休市 state with the snapshot date. Network errors are surfaced through `status.error/notice` instead of crashing the page.

## Data integrity (data health)
- `GET /api/data/integrity?snapshot=<id|prefix>` → `{status:"ok"|"warn"|"fail",generated_at,snapshot:{id,synthetic,source,n_sec,n_time,start,end}|null,coverage:{expected_cells,present_cells,coverage_pct,symbols,trading_days},checks:[{id,title,status:"pass"|"warn"|"fail",detail}],gaps:{missing_days,symbols_with_gaps,examples:[{code,date}]},accuracy:{ohlc_violations,volume_amount_mismatch,limit_violations,adjustment_breaks},cross_source:{checked,matched,max_rel_diff,source,note},note}`
- Read-only and offline: audits the current snapshot panel (coverage by listing date, gaps/suspensions, OHLC invariants, limit-up/down consistency, adjustment continuity). `snapshot` omitted → latest snapshot or the explicit synthetic fallback (marked `snapshot.id="synthetic"`). Unknown snapshot → 404.
- `cross_source` is skipped offline (`checked=0`, note says so); it is a hook for explicit cross-source spot checks, not a network call in the default path.
- UI: 数据页「数据体检」卡片 / 首页摘要 / 回测结果页的可信度徽章 use this route; a `warn`/`fail` status must be shown rather than silently ignored.

## Beginner onboarding + watchlist
- `GET /api/onboarding` → `{first_run,beginner,steps:[{id:"data"|"backtest"|"result"|"data_health",title,description,action:"bootstrap"|"backtest"|"browse"|"data",label,done}],progress:{done,total}}`
  - `done` is auto-detected (snapshot exists → data; experiment exists → backtest/result) plus explicit completed steps stored in SQLite meta; `first_run` flips after the first record.
- `POST /api/onboarding/complete` `{step:<id>}` → updated state (idempotent; unknown step 400). `POST /api/onboarding/reset` → initial state.
- `GET /api/onboarding/presets` → `[{id,name,tagline,description,plain_terms,risk_note,template,params,horizon,suitable_for}]`; templates/params are real built-in strategies (validated by tests), plain-language copy is UI copy, not investment advice.
- `GET /api/watchlist` → `{codes:["600000",…]}`; `PUT /api/watchlist` `{codes:[…]}` → validated (6 ASCII digits, deduped, ≤50, invalid → 400) and persisted in SQLite meta. The live quote poller subscribes to this list.

## Screener
- `GET /api/screener/presets` → `[{id,name,description,expression}]`
- `POST /api/screener/run` body `{snapshot?,expression,universe?:{boards?,exclude_st?,exclude_suspended?,min_amount?,min_list_days?},limit?}` →
  `{as_of,universe_count,matched_count,rows:[{sec_id,code,name,board,industry,close,change_pct,turnover,mktcap,score}]}`
- `GET /api/screener/saved` / `POST /api/screener/saved` (optional; UI localStorage fallback)

## Strategies
- `GET /api/strategies/templates` → `[{id,name,description,params_schema}]`
- `GET /api/strategies/templates/{id}` → one template
- `POST /api/strategies/validate` body `{template,params}` → `{valid,errors[],defaults}`
- `GET /api/strategies/files` / `GET|PUT /api/strategies/files/{name}` (strategy.yaml + strategy.py; optional M6)

## Backtest / jobs
- `POST /api/backtest` body `{template|strategy|source_run_id,snapshot?,params?,config?,snapshots_root?,experiments_root?}` → 202 `{job_id,status}`
  - `source_run_id` reuses the saved experiment's snapshot or persisted panel, strategy and configuration. It cannot be combined with `snapshot` or `synthetic`; missing source data fails rather than generating a replacement. Overrides to `costs`/`exec`/`rules`/`risk` merge with the recorded values. Each new run records `metadata.parent_run_id`; the source is unchanged. An explicit template selects new parameters while preserving the original universe for the same template. Both source validation and execution use the effective `experiments_root`.
- `GET /api/jobs?status=&limit=` → `[JobView]`
- `GET /api/jobs/{id}` → `JobView`
- `POST /api/jobs/{id}/cancel` → `{job_id,cancelled:boolean,status}`
- `GET /api/jobs/{id}/result` → `{job_id,status,result}` or 202/409
- `WS /ws/jobs/{id}?token=` → messages `{type:"job",job:JobView}`, `{type:"done",job:JobView}`, `{type:"error",error}`
- `POST /api/backtest/replay` body `{run_id}`? use experiments replay.

JobView result for backtest includes `run_id`, `engine_backend`, `engine_version`, `metrics`, `trade_count`, `final_equity`, `snapshot`, `synthetic`.

## Experiments
- `GET /api/experiments?limit=&kind=` → `[{run_id,created_at,status,kind,strategy_name,template,snapshot_id,content_hash,metrics,tags,note}]`
- `GET /api/experiments/{run_id}` → `{metadata,summary,metrics,result:{dates[],equity[],cash[],market_value[],trades[]}}`
- `GET /api/experiments/{run_id}/result` → full `{dates[],equity[],cash[],market_value[],trades[],metrics,reasons}`
  - Also returns the saved `config`, `snapshot` and `synthetic` provenance (`null` when not recorded), so changing the current workspace does not relabel an old result.
- `POST /api/experiments/{run_id}/replay` → `{run_id,matched,equity_matched,trades_matched,metrics_matched,diffs[]}`
- `GET /api/experiments/{run_id}/report` → HTML (text/html)
- `GET /api/experiments/{run_id}/export` → zip download
- `GET /api/experiments/compare?ids=a,b` → `{ids[],metrics:{...},equity:[{run_id,dates[],equity[]}]}`
  - Existing raw curves remain unchanged. Each curve additionally returns `initial_cash`, `normalized_equity` (equity / recorded initial cash), fractional `drawdown`, `label` and `provenance` (data/strategy hashes, settings, source, engine, code revision, parent run).
  - `comparison` contains `{status,dimensions[],warnings[]}`. Each dimension is `{key,label,status,values:{run_id:value}}`; statuses are `matched`, `different` or `unknown`. Actual trading dates (including interior gaps), data, capital, costs, execution, rules, corporate actions, risk, annualization, benchmark and engine are checked. Strategy differences are intentional and displayed separately. Matching conditions do not certify market data or strategy quality.
  - Missing capital means `normalized_equity:null`, never first-observation rebasing. Drawdown includes starting capital when recorded; legacy records use the first observed equity. Dates are not interpolated or truncated; duplicate IDs are rejected and at most six distinct runs may be requested (UI: four).
- `DELETE /api/experiments/{run_id}`

## Data
- `GET /api/data/status` → `{data_root,warehouse:{exists,datasets,rows,bytes,manifest_hash},snapshots:[{id,content_hash,created_at,synthetic,n_sec,n_time,fields,quality}],storage:{warehouse_bytes,snapshot_bytes,experiments_bytes,free_bytes},providers:[...]}`
- `GET /api/data/providers` → `[{id,name,requires_token,requires_network,available,capabilities}]`
- `POST /api/data/update` body `{provider,start?,end?,n_sec?,seed?,local_dir?,fixture_dir?,codes?,limit?,incremental?,reset?}` → 202 `{job_id}`. Incremental imports require the same source identity and code scope; changing them requires explicit replacement. Reset fetches and validates before clearing old datasets. Warehouse identity lives in `warehouse_manifest.json`, shared by CLI and API regardless of the jobs database.
- `POST /api/data/snapshot` body `{data_root?,snapshots_root?,require_qpanel?}` → 202 `{job_id}`
- `GET /api/data/snapshots` → snapshot list
- `GET /api/data/quality?snapshot=` → quality report
- `POST /api/onboarding/bootstrap` body `{n_sec?,start?,end?,seed?}` → `{snapshot,snapshot_dir,run_id,report,message}` (synchronous)

## Research (M7)
- `POST /api/research/factor` body `{snapshot?,expression,forward_days=5,quantiles=5}` → `{name,expression,forward_days,quantiles,ic_mean,rank_ic_mean,icir,rank_icir,ic_series:[{date,ic,rank_ic}],quantile_returns:[{bucket,mean_return(小数),observations}],decay:[{days,ic,rank_ic}],coverage,observations,synthetic}`
- `POST /api/research/sweep` body `{template,param_grid,snapshot?,start?,end?,initial_cash?,workers?}` → `{template,points:[{params,metrics,error}],best,engine_backend,bounded_points,synthetic}` (bounded; sync for ≤200 combos)
- `POST /api/research/walk_forward` body `{template,params,snapshot?,folds?}` → `{template,params,folds:[{fold,start,end,trading_days,trade_count,metrics}],engine_backend,synthetic}`
- `POST /api/research/attribution` body `{run_id}` → `{run_id,strategy_name,industries:[{industry,pnl,realized,unrealized,market_value,weight,securities}],synthetic}`

## Errors
`{detail:string|object}`; 400 validation, 401/403 auth, 404, 409 conflict, 422 pydantic/template validation, 500 internal (no stack in body).

## Paper trading (M9, local simulation only — no real orders)
- `POST /api/paper/sessions` body `{mode?:"historical"|"live",snapshot?,initial_cash?,start?,end?,name?}` → **201** session view
- `GET /api/paper/sessions` → list; `GET /api/paper/sessions/{sid}` → `{session,snapshot,account:{cash,market_value,equity,pnl,pnl_pct},positions[],orders[],trades[],equity_curve[]}`
- `POST /api/paper/sessions/{sid}/step` body `{}`/`{days}`/`{to_date}` → detail + `fills[]`; `POST .../reset`
- `POST .../orders` body `{code|sec_id,side:"buy"|"sell",qty,order_type:"market"|"limit",limit_price?}` → `{order}`
- `POST .../orders/{oid}/cancel`; `GET .../signals.csv`; `DELETE /api/paper/sessions/{sid}`
- `mode` defaults to historical; old sessions remain historical. Historical mode needs a snapshot and fills on the next `step` at the next open / limit touch. Live creation needs no snapshot; snapshot/start/end do not determine live execution.
- `POST /api/paper/sessions/{sid}/refresh` (no body) → detail + `fills[]` + `live:{state,as_of,notice,quotes[]}` for live sessions only (historical → 400). The route reads public quotes for holdings/open orders and persists valuation, observations and virtual fills. Each position can include `quote_timestamp`.
- Live matching requires enabled quotes, an open market, valid fresh source timestamps and post-order incremental volume (default shared 10% budget per security). First observations, source/date changes and long gaps establish a baseline; repeated quotes and cumulative-volume rollback do not create new capacity. See [paper semantics](paper-trading.md) for exact age/gap/limit rules.
- Board lots, T+1, price limits, suspensions, fees and cancellation apply. Sessions persist as atomic JSON under `data_root/paper/`. Only refresh requests match live orders: the selected open UI page requests them every 3s; the quote poller alone does not. No broker, real orders, order book or corporate-action processing.

## Research robustness (M7 advanced)
- `POST /api/research/overfitting` `{run_id,n_trials?}` → `{observations,periods_per_year,sharpe,deflated_sharpe,expected_max_sharpe,n_trials,skew,kurtosis,verdict}`
- `POST /api/research/pbo` `{run_ids:[],n_splits?:8}` → `{run_ids,n_splits,combinations,pbo,median_oos_rank,logits[][]}`。公开 OOS 排名 1 为最好；内部 logit 使用并列平均秩，较好表现对应正值。PBO 按 `logit <= 0` 统计未胜过 OOS 中位数的比例，中位并列计入；完全相同的实验不会被视为独立的稳健证据。
- `POST /api/research/cost_sensitivity` `{run_id,multipliers?:[0,0.5,1,2,3]}` → `{run_id,points:[{multiplier,total_return,annualized_return,sharpe,max_drawdown,total_fees}],breakeven_multiplier?}`。费用倍数是情景标签，保留小数；收益和回撤为小数，`total_fees` 为 1e-4 元定点值，界面转为元。原实验不被修改。
- `POST /api/research/monte_carlo` `{run_id,n_paths?:500,horizon?:250}` → `{terminal_return:{p05,p25,p50,p75,p95},max_drawdown:{p05,p50,p95},paths?}` (block=20, deterministic seed)
- `POST /api/research/capacity` `{run_id,adv_participation?:0.1}` → `{capacity_cny,participation,avg_turnover,avg_adv_cny,limiting_sec,notes}`; approximate, 400 when data is missing

## M7 factor correlation / random sweep
- `POST /api/research/factor_correlation` `{expressions:[2..10], snapshot?, start?, end?, method?:"pearson"|"spearman"}` → `{expressions,labels,matrix, average_abs_correlation, observations, periods, dates, method, note}`; daily cross-sectional mean correlation over common tradable support.
- `POST /api/research/sweep` now accepts `{mode?:"grid"|"random", sample_size?:0..200, seed?:42}`; random mode samples without replacement and returns `sampling:{mode,requested,returned,seed}`; grid mode semantics unchanged (max 200).

## Local strategy plugins (M9)
- `GET /api/strategies/plugins` → list `data_root/strategies/*.py` with `valid/issues/interface/description/version`; static AST audit, no import during listing.
- `POST /api/strategies/plugins/{name}/validate` → `{valid,issues,interface,policy}`; path traversal/non-.py → 404.
- `POST /api/strategies/plugins/{name}/backtest` `{params?,snapshot?,start?,end?,initial_cash?}` → **202** `{job_id,status,plugin}`; job runs through the normal backtest queue and persists experiment metadata `plugin`.
- Policy: local trusted plugins only, static audit is not a hard security boundary; no network, no real orders. `params` are recorded in the experiment spec but the current loader does not pass them into the plugin body.

## Benchmark comparison (M3)
- Backtest `config.benchmark_code` (optional local security code) → fractional buy-and-hold benchmark, using effective cash/split events, retaining dividends as cash, with no costs or tax. Panel events default on via `use_panel_corporate_actions`; explicit events override the same security/ex-date.
- Result payloads include `benchmark:{code,sec_id,name,dates,equity,total_return,daily_observations,complete_window,definition,metrics}` and metrics `benchmark_return/excess_return/tracking_error/information_ratio`; persisted as `result/benchmark.json`. Gaps remain null; daily tracking metrics use only adjacent valid prices and return null with insufficient observations. Missing endpoint prices set `complete_window=false` and `excess_return=null`.

## Risk limits (M3)
- Backtest `config.risk` accepts `{max_positions?: int, max_weight?: float (0,1], long_only?: bool=true}`.
- Target weights are clamped/limited before the C++ engine runs; long-only by default, negative targets set to 0. Output/metrics remain engine-native.

## Paper portfolio (M9, read-only)
- `POST /api/paper/portfolio` `{allocations:[{session_id,weight>0}] (2..10), initial_cash?}` → `{allocations,dates,equity,normalized_equity,metrics:{total_return,annualized_return,volatility,sharpe,max_drawdown},contributions,note}`.
- Strict intersection of session equity-curve dates; each session normalized by starting cash, weighted, rebased to `initial_cash` on the first common date. Read-only: no mutation, no orders, weights must sum to 1 (400 otherwise); unknown/duplicate session 404/400.

## PIT financial view (M2)
- `GET /api/market/financials/{code}?as_of=YYYY-MM-DD&limit=20` → `{code,sec_id,as_of,latest,rows,note}`; only reports with `ann_date <= as_of` (point-in-time, no restatement reconstruction), newest first.

## Report export (M4)
- `GET /api/experiments/{run_id}/report` → HTML; `GET /api/experiments/{run_id}/report.pdf` → PDF via local Chrome/Chromium print-to-pdf (503 with `{detail}` when no browser is installed; optional, not required for research runs).

## Plugin execution isolation (M4)
- Local plugin backtest jobs set `sandbox_worker=true`: custom strategy code runs in a child Python process (`quantcore.strategy.worker`) with CPU/file-size limits, loads one immutable snapshot, writes a weights `.npy`, and the engine runs in the parent. Static AST audit remains the interface check; this is process isolation, not a multi-tenant security boundary.

## Paper auto-run (M9, simulated clock)
- `POST /api/paper/sessions/{sid}/auto` `{interval_ms?:50..60000, days_per_tick?:1..30}` starts a server-side simulated clock that steps the existing historical session (live mode → 400; no live market feed); `POST .../auto/stop`; `GET .../auto` status.
- Runs are daemon threads, persist each step, stop at session end/delete; UI button and 1s polling while active.

## V2 datasets (M8-005)
- `GET /api/data/catalog` returns the v2 catalog: daily_bars, minute_bars (SYNTHETIC view), securities, financials, corporate_actions and snapshots, with grain/storage/fields and caveats.
