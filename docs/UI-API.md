# UI ⇄ API contract v2 (enterprise local workbench)

All routes are loopback-only, Bearer-authenticated (`Authorization: Bearer <token>`), JSON.
The built UI is served by `qc serve` from the same origin, so no CORS is needed. For Vite dev,
`vite.config.ts` proxies `/api`, `/ws`, `/health` to `http://127.0.0.1:8000`.

WebSocket: `ws://127.0.0.1:<port>/ws/jobs/<job_id>?token=<token>`; server validates Origin/Host/token.

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
  "root": "/Users/me/QuantCore",
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
- `GET /api/market/securities?snapshot=&query=&limit=200` →
  `[{sec_id,code,name,board,industry,last,change_pct,turnover,mktcap,float_mktcap,suspended,st}]`

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
- `POST /api/backtest` body `{template|strategy,snapshot?,params?,config?,snapshots_root?,experiments_root?}` → 202 `{job_id,status}`
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
- `POST /api/experiments/{run_id}/replay` → `{run_id,matched,equity_matched,trades_matched,metrics_matched,diffs[]}`
- `GET /api/experiments/{run_id}/report` → HTML (text/html)
- `GET /api/experiments/{run_id}/export` → zip download
- `GET /api/experiments/compare?ids=a,b` → `{ids[],metrics:{...},equity:[{run_id,dates[],equity[]}]}`
- `DELETE /api/experiments/{run_id}`

## Data
- `GET /api/data/status` → `{data_root,warehouse:{exists,datasets,rows,bytes,manifest_hash},snapshots:[{id,content_hash,created_at,synthetic,n_sec,n_time,fields,quality}],storage:{warehouse_bytes,snapshot_bytes,experiments_bytes,free_bytes},providers:[...]}`
- `GET /api/data/providers` → `[{id,name,requires_token,requires_network,available,capabilities}]`
- `POST /api/data/update` body `{provider,start?,end?,n_sec?,seed?,local_dir?,fixture_dir?,incremental?,reset?}` → 202 `{job_id}`
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
- `POST /api/paper/sessions` body `{snapshot?,initial_cash?,start?,end?,name?}` → **201** session view
- `GET /api/paper/sessions` → list; `GET /api/paper/sessions/{sid}` → `{session,snapshot,account:{cash,market_value,equity,pnl,pnl_pct},positions[],orders[],trades[],equity_curve[]}`
- `POST /api/paper/sessions/{sid}/step` body `{}`/`{days}`/`{to_date}` → detail + `fills[]`; `POST .../reset`
- `POST .../orders` body `{code|sec_id,side:"buy"|"sell",qty,order_type:"market"|"limit",limit_price?}` → `{order}`
- `POST .../orders/{oid}/cancel`; `GET .../signals.csv`; `DELETE /api/paper/sessions/{sid}`
- Orders fill on the next `step` at the next open / limit touch; board lots, T+1, price limits, suspensions and fee model are reused from backtest config. Sessions persist as atomic JSON under `data_root/paper/`; no broker, no network.

## Research robustness (M7 advanced)
- `POST /api/research/overfitting` `{run_id,n_trials?}` → `{observations,periods_per_year,sharpe,deflated_sharpe,expected_max_sharpe,n_trials,skew,kurtosis,verdict}`
- `POST /api/research/pbo` `{run_ids:[],n_splits?:8}` → `{run_ids,n_splits,combinations,pbo,median_oos_rank,logits[][]}`
- `POST /api/research/cost_sensitivity` `{run_id,multipliers?:[0,0.5,1,2,3]}` → `{points:[{multiplier,total_return,annualized_return,sharpe,max_drawdown,total_fees}],breakeven_multiplier?}`; original experiment is never modified
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
- `POST /api/config` / backtest `config.benchmark_code` (optional security code) → buy-and-hold benchmark over the same result dates.
- Result payloads include `benchmark:{code,sec_id,name,dates,equity,total_return,metrics}` and metrics `benchmark_return/excess_return/tracking_error/information_ratio`; persisted as `result/benchmark.json` and included in job/experiment result payloads.

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
- `POST /api/paper/sessions/{sid}/auto` `{interval_ms?:50..60000, days_per_tick?:1..30}` starts a server-side simulated clock that steps the existing historical session (no live market feed); `POST .../auto/stop`; `GET .../auto` status.
- Runs are daemon threads, persist each step, stop at session end/delete; UI button and 1s polling while active.

## V2 datasets (M8-005)
- `GET /api/data/catalog` returns the v2 catalog: daily_bars, minute_bars (SYNTHETIC view), securities, financials, corporate_actions and snapshots, with grain/storage/fields and caveats.
