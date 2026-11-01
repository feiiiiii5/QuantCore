# UI ⇄ API contract v2 (enterprise local workbench)

All routes are loopback-only, Bearer-authenticated (`Authorization: Bearer <token>`), JSON.
The built UI is served by `qc serve` from the same origin, so no CORS is needed. For Vite dev,
`vite.config.ts` proxies `/api`, `/ws`, `/health` to `http://127.0.0.1:8765`.

WebSocket: `ws://127.0.0.1:<port>/ws/jobs/<job_id>?token=<token>`; server validates Origin/Host/token.

## Meta / health
- `GET /health` → `{status,version,engine_backend,engine_available,panel_available,synthetic_only,cors}`
- `GET /api/meta` → `{version,engine_backend,synthetic_only,data_root,snapshots_root,experiments_root,token_required,ui_served}`

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
- `POST /api/research/factor` body `{snapshot?,expression,forward_days=5,quantiles=5}` → `{name,ic_mean,rank_ic_mean,icir,ic_series:[{date,ic,rank_ic}],quantile_returns:[{bucket,mean_return}],decay:[{days,ic}],coverage,observations}`
- `POST /api/research/sweep` body `{template,param_grid,snapshot?,start?,end?,initial_cash?,workers?}` → `{points:[{params,metrics}],best,heatmap?}` (bounded; sync for ≤200 combos)
- `POST /api/research/walk_forward` body `{template,params,snapshot?,folds?}` → folds metrics (basic)
- `POST /api/research/attribution` body `{run_id}` → factor/industry contribution (basic; 501 until implemented if not)

## Errors
`{detail:string}`; 400 validation, 401/403 auth, 404, 409 conflict, 422 pydantic, 500 internal.
