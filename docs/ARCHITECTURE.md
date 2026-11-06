# ARCHITECTURE — QuantCore 企业级本地架构

```
┌────────────────────────────── macOS / Windows / Linux (single user) ──────────────────────────────┐
│  React 19 + Vite UI (ui/)  ──HTTP/WS, same origin, Bearer──►  FastAPI qc-server (python/quantcore/server) │
│       │  lightweight-charts / Radix UI / framer-motion / Monaco        │                                  │
│       │  loading/error/empty states, zh-CN, theme tokens               │  /api/market /screener /strategies │
│       │                                                                │  /backtest /jobs /experiments        │
│       └────────────────────────── Vite dev proxy / static SPA ────────┘  /data /research /onboarding       │
│                                                                          │                                  │
│                                              ┌───────────── SQLite state (WAL, migrations) ─────────────┐  │
│                                              │ jobs / snapshots / datasets / watermarks / meta          │  │
│                                              └──────────────────────────────────────────────────────────┘  │
│                                                          │                                                │
│  ┌─────────────── job worker (single thread, cooperative cancel) ─────────────────────────────────────┐  │
│  │ backtest / data update / snapshot build / research jobs  →  ExperimentStore / ParquetStore          │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                          │                                                │
│  Data plane:  Provider → ingest/quality → Parquet partition + DuckDB query + SQLite state → snapshot       │
│                                    → manifest + .qpanel (C++ PanelWriter, mmap)                            │
│                                                          │                                                │
│  qcore (C++20, pybind11): fixed-point panel/kernels/expression/engine/analytics; Python reference only in  │
│  tests/reference; production backtests always go through _qcore.Engine.                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 进程与边界
- UI 与 API 同源：`qc serve` 托管 `ui/dist`（SPA fallback），开发时 Vite proxy `/api`、`/ws`、`/health` 到 127.0.0.1。
- API 仅绑定 127.0.0.1；每次启动随机 Bearer token（可 `QC_SERVER_TOKEN` 固定）；校验 Host/Origin；无通配 CORS。
- WebSocket `/ws/jobs/{id}?token=` 推送任务进度；HTTP 轮询有相同 JobView；Backtest 页面优先 WS，连接失败回退轮询，错误帧中的终态也会完成任务跟踪。
- 任务执行在独立 worker 线程；普通异常通过 job status + error 回传，原生进程崩溃仍可能终止服务。启动时恢复 running→failed；关闭时协作取消当前任务，等待超时仍保留线程引用，防止重复 worker。
- 策略/自定义脚本运行于受控 loader；自定义策略经子进程 worker（`strategy/worker.py` + `strategy/sandbox_worker.py`，POSIX 下 CPU/文件大小 rlimit）隔离；仍属本地信任模型，不是对抗恶意代码的强沙箱；默认无网络/写工作区外。

## 数据流
1. Provider（Synthetic/LocalFile/Tushare fixture/AKShare/mootdx）→ `ProviderIngestor`：限流、重试、增量水位、幂等。
2. 质量门禁（缺失/重复/价格自洽/单位/复权/涨跌停互校/PIT）→ 坏行隔离；失败不建快照。
3. Parquet 分区为权威数据；DuckDB 只读查询；SQLite 存应用状态（jobs/snapshots/datasets/watermark）。
4. 快照 `snap_<hash16>` 不可变、内容寻址、manifest 含来源/版本/质量/schema；`panel.qpanel` 由 C++ PanelWriter 生成。
5. 引擎只读快照；策略由 Python 生成 `(n_time,n_sec)` 目标权重；C++ 引擎执行规则/费用/T+1/账本/trace/metrics。
6. 实验目录保存 metadata/summary/result parquet/report.html/strategy.yaml；replay 逐位对比 equity/trades/metrics。
7. `source_run_id` 从原实验加载已保存数据并保留隐藏的规则/费用设置，生成新实验与父记录链接；实验比较使用记录的初始资金归一化，明确列出不同或缺失的研究条件。

## 前端信息架构
- 壳：八页导航（行情/选股/策略/回测/实验/研究/模拟/数据）+ 设置；顶部全局搜索（⌘K 聚焦）；底部状态栏；主题/密度/涨跌配色。
- 行情：overview 指数/宽度/行业；K 线（lightweight-charts）；证券搜索/虚拟表格。
- 选股：表达式/预设 → 结果表 → CSV 导出/localStorage 方案。
- 策略：模板 + JSON Schema 表单 + Monaco + validate/运行。
- 回测：表单 → job → 轮询/WS 进度/取消 → 指标/净值回撤/逐笔/费用/交易解释 → replay/报告。
- 实验：列表/详情/归一化对比/假设差异/来源记录/replay/报告/导出/删除，支持沿用数据参数与继续稳健性研究。
- 研究：因子分析/参数 sweep/滚动验证/归因/稳健性（DSR/PBO/成本敏感性/MC/容量）。
- 模拟：虚拟账户/逐日回放/委托撤单/成交/信号 CSV/提醒/多策略只读组合/服务端模拟时钟（非实时行情、不接券商）。
- 数据：源状态、更新、快照、质量、存储、onboarding。
- 设置：API 地址/Bearer token、主题/密度/涨跌配色。
- 所有页面 loading/error/empty/retry；免责声明固定；无 CDN/远程字体。

## 可观测性与质量
- 后端：结构化错误 `{detail}`、请求日志（脱敏）、job error 堆栈摘要、OpenAPI。
- 前端：ErrorBoundary、请求错误 toast、空态、骨架屏；E2E 截图 + console error 检查。
- 测试：C++ Catch2（95）、Python pytest（差分/属性/黄金/API/WS）、UI Vitest、Playwright E2E、`make ci-local` / `verify-cpp`。
- CI：GitHub Actions macOS+Ubuntu core + UI build/test；Playwright E2E 在本地 `make e2e`（需 Chrome），未纳入 GitHub CI。

## 失败模式
| 场景 | 行为 |
|---|---|
| 无快照 | market 使用明确标注的 synthetic fallback；backtest 用 synthetic；UI 显示“SYNTHETIC”横幅 |
| 数据源无 Token/网络 | provider 返回 ProviderUnavailable；job failed + 脱敏错误；不阻塞其他功能 |
| C++ 扩展缺失 | `/health` engine_available=false；backtest 400 明确提示 `make build` |
| 任务取消 | pending 立即 cancelled；running 在检查点抛 JobCancelled -> cancelled；临时文件/实验清理 |
| 服务崩溃 | 启动时 running→failed（error 标记 recovered）；UI 可重试 |
| 端口被占用 | uvicorn 报错退出并打印；UI 连接失败显示设置引导 |

## 目录
见 `AGENTS.md`；API 契约见 `docs/UI-API.md`；语义见 `docs/engine-semantics.md`。
