# PROGRESS — 当前进度

> 每阶段结束记录：完成项、验证命令与结果、已知缺口、下一步、续跑方法。上下文清空后据此恢复。
> 更新时间：2026-11-02。

## 当前状态
- M0：完成。`make setup/test`、wheel、macOS/Ubuntu 全量 CI + Windows pure-Python smoke；C++ Windows 未支持。
- M1：C++ types/calendar/tpool/.qpanel/内核/指标/零拷贝绑定；ctest 95/95；cross-sectional neutralize 已实现并绑定。
- M2：Synthetic/LocalFile/Tushare(fixture+live API 代码路径)/AKShare/mootdx；摄取/质量/快照(内容寻址+PIT 元数据)/Parquet+DuckDB+SQLite；PIT 财务视图；真实 Tushare Token 未验证。
- M3：event-driven 引擎，规则/费用/T+1/手数/涨跌停/停牌/除权除息/trace/指标；差分 6/6；风险限制/基准比较；引擎 300×965 月度调仓约 2.6ms。
- M4：DSL/7 模板/lookahead/实验存储/HTML+可选 PDF 报告/CLI/replay/子进程 sandbox worker/C++ parallel engine batch sweep。
- M5：FastAPI UI-API v2；SQLite 任务队列、协作取消、崩溃恢复、WebSocket、Bearer/Host/Origin/no-CORS、GZip；`qc serve` 同源托管 UI；本地 toast/桌面通知。
- M6：React 19 + Vite 八页（行情/选股/策略/回测/实验/研究/模拟/数据 + 设置）；ECharts 图表、Monaco 本地打包、交易解释、onboarding、浅/深色、密度、移动端；Playwright **18** 条通过（含 paper/多策略组合/稳健性/插件）。
- M7：因子 IC/RankIC/ICIR、分层、衰减；参数扫描 + Sharpe 热力图；滚动验证；行业 FIFO 归因；Deflated Sharpe/PBO、成本敏感性、block bootstrap Monte Carlo、容量估计（近似口径）。
- M9：大部分完成——本地虚拟账户/逐日回放/委托撤单/成交/T+1/费用/信号 CSV/提醒/JSON 持久化/本地插件/只读多策略组合/服务端模拟时钟自动推进；真实实时行情 feed 仍未接。
- M8：部分完成——证券资料扩展、PIT 财务视图；分钟线/ETF/可转债/V2 datasets 未做。
- M10：wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS app zip；Windows 包未在 Windows 验证、无签名/公证。
- 仓库：https://github.com/feiiiiii5/QuantCore （Apache-2.0）；申请季工作区未修改。

## 本轮实际验证
```bash
cd /Users/fei/Desktop/QuantCore
make lint
# ruff check/format 通过；mypy 85 files 无问题

uv run pytest -q -p no:warnings
# 194 collected；192 passed / 2 skipped

pnpm -C ui test
# 7 passed (4 files)

pnpm -C ui build
# 通过；初始 JS 约 1.4 MB raw，Monaco 3.3 MB 按路由懒加载

make e2e
# 构建 UI + 隔离 qc serve + Playwright 18 passed：
# 行情/选股/回测/实验/数据/策略/设置/研究/稳健性/插件/模拟/组合/onboarding/暗色/移动端/性能

uv run python scripts/verify_cpp.py
# C++ backend、差分 6/6、open 0.18ms、20 factors 21ms、engine 2.6ms、ratio 160x+
```

## 本轮修复/新增
- M9 模拟交易：虚拟账户/回放/委托撤单/成交/CSV/提醒/本地插件/多策略组合/模拟时钟。
- M7 稳健性：DSR/PBO/成本敏感性/Monte Carlo/容量、因子相关性、随机扫描。
- M3：基准比较（净值/超额/跟踪误差/IR）与目标权重风险限制。
- M8：证券资料扩展、PIT 财务视图。
- M4：可选 PDF（本地 Chrome）、子进程 strategy worker、C++ parallel engine sweep。
- M10：SBOM/pip-audit、release/perf gate、Electron dev shell（headless smoke 验证 UI 加载）。
- 测试：pytest 187 collected/185 passed/2 skipped；UI vitest 7；Playwright 18。

## 已知缺口
1. M8：分钟线、ETF/可转债、V2 datasets。
2. M9：真实实时行情 feed、部分成交/公司行为。
3. M10：macOS/Windows 安装包与签名；Windows CI 未验证。
4. M2：实时 Tushare（无 Token 验证）；全市场 5500×20y 基准与峰值 RSS 未测。
5. 规则 TODO(verify) 仍需外部核实。
6. `docs/features.json` **109/117**；不得声称完整。

## 续跑方法
```bash
cd /Users/fei/Desktop/QuantCore
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
make setup
make ci-local
make e2e
make desktop-smoke   # 可选
uv run qc serve --port 8000 --open
```
