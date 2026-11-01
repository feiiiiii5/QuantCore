# PROGRESS — 当前进度

> 每阶段结束记录：完成项、验证命令与结果、已知缺口、下一步、续跑方法。上下文清空后据此恢复。
> 更新时间：2026-11-02。

## 当前状态
- M0：完成。`make setup/test`、wheel、macOS/Ubuntu CI；Windows 未纳入。
- M1：C++ types/calendar/tpool/.qpanel/内核/指标/零拷贝绑定；ctest 95/95。neutralize 尚未实现（features M1-008=false）。
- M2：Synthetic/LocalFile/Tushare(fixture)/AKShare/mootdx；摄取/质量/快照(内容寻址+PIT 元数据)/Parquet+DuckDB+SQLite；合成全市场快照可建。
- M3：event-driven 引擎，规则/费用/T+1/手数/涨跌停/停牌/除权除息/trace/指标；差分 6/6；引擎 300×965 月度调仓约 2.6ms。
- M4：DSL（tokenizer/parser/CSE/eval）、7 模板、lookahead/sandbox 接口、实验存储/HTML 报告、CLI backtest/replay；C++ 并行 sweep、PDF 未做。
- M5：FastAPI UI-API v2；SQLite 任务队列、协作取消、崩溃恢复、WebSocket、Bearer/Host/Origin/no-CORS、GZip；`qc serve` 同源托管 UI；本地 toast/桌面通知。
- M6：React 19 + Vite 八页（行情/选股/策略/回测/实验/研究/模拟/数据 + 设置）；ECharts 图表、Monaco 本地打包、交易解释、onboarding、浅/深色、密度、移动端；Playwright **16** 条通过（含 paper/稳健性）。
- M7：因子 IC/RankIC/ICIR、分层、衰减；参数扫描 + Sharpe 热力图；滚动验证；行业 FIFO 归因；Deflated Sharpe/PBO、成本敏感性、block bootstrap Monte Carlo、容量估计（近似口径）。
- M9：基础完成——本地虚拟账户/逐日回放/委托撤单/成交/T+1/费用/信号 CSV/JSON 持久化；无持续实时/提醒/多组合/插件。
- M8：未实现；M10 Electron/安装包/SBOM/Windows 未做。
- M10：wheel + UI 构建 + 中文文档 + 许可；Electron/安装包/SBOM/Windows 未做。
- 仓库：https://github.com/feiiiiii5/QuantCore （Apache-2.0）；申请季工作区未修改。

## 本轮实际验证
```bash
cd /Users/fei/Desktop/QuantCore
make lint
# ruff check/format 通过；mypy 69 files 无问题

uv run pytest -q -p no:warnings
# 151 collected；149 passed / 2 skipped

pnpm -C ui test
# 7 passed (4 files)

pnpm -C ui build
# 通过；初始 JS 约 1.4 MB raw，Monaco 3.3 MB 按路由懒加载

make e2e
# 构建 UI + 隔离 qc serve + Playwright 14 passed：
# 行情/选股/回测/实验/数据/策略/设置/研究/onboarding/暗色/移动端/性能

uv run python scripts/verify_cpp.py
# C++ backend、差分 6/6、open 0.18ms、20 factors 21ms、engine 2.6ms、ratio 160x+
```

## 本轮修复
- `ui_fallback` 的 `Request` 注解导致 favicon/SPA 路由 422；改为无 request 参数。
- 快照 manifest `start/end` 为日期字符串时行情接口 500；统一 `_date_text`。
- Monaco 默认 CDN 加载导致策略页一直 Loading；改为本地 `monaco-editor` + worker，并按路由懒加载。
- ECharts 使用 `var(--up/--down)` 在 canvas 无效；统一解析 CSS 变量，暗色主题重初始化。
- 量化分层收益单位（小数→百分比）修正。
- 交易解释面板接入逐笔费用/触发原因。
- `qc serve --open` 的 `?token=` 未持久化；入口读取后写入 localStorage 并清理 URL。
- Vite dev 无代理；补 `/api` `/ws` `/health` 到 8000。
- GZip 中间件；UI 性能预算测试。
- 新增 API v2/研究/任务/数据/onboarding 测试与 Playwright。

## 已知缺口
1. M9 进阶：持续实时模拟、提醒、多组合、插件、部分成交/公司行为。
2. M8 分钟线、ETF/可转债、板块规则、PIT 财务视图。
3. M7 Deflated Sharpe/PBO、成本敏感性、bootstrap/Monte Carlo、容量。
4. M10 Electron/安装包/SBOM/审计/Windows CI。
5. 真实 Tushare、全市场基准/峰值 RSS/覆盖率。
6. 规则 TODO(verify) 仍需外部核实。
7. `docs/features.json` **80/117**；不得声称完整。

## 续跑方法
```bash
cd /Users/fei/Desktop/QuantCore
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
make setup
make ci-local
make e2e
uv run qc serve --port 8000 --open
```
