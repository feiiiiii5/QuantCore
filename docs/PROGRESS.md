# PROGRESS — 当前进度

> 每阶段结束记录：完成项、验证命令与结果、已知缺口、下一步、续跑方法。上下文清空后据此恢复。
> 更新时间：2026-11-02。
> 交接记录（2026-11-02）：上一会话交接文档的独有信息已并入本文件，交接文件已删除；续跑以本文件为准。

## 当前状态
- M0：完成。`make setup/test`、wheel、macOS/Ubuntu 全量 CI + Windows pure-Python smoke；C++ Windows 未支持。
- M1：C++ types/calendar/tpool/.qpanel/内核/指标/零拷贝绑定；ctest 95/95；cross-sectional neutralize 已实现并绑定。
- M2：Synthetic/LocalFile/Tushare(fixture+live API 代码路径)/AKShare/mootdx；摄取/质量/快照(内容寻址+PIT 元数据)/Parquet+DuckDB+SQLite；PIT 财务视图；真实 Tushare Token 未验证。
- M3：event-driven 引擎，规则/费用/T+1/手数/涨跌停/停牌/除权除息/trace/指标；差分 6/6；风险限制/基准比较；引擎 300×965 月度调仓约 2.6ms。
- M4：DSL/7 模板/lookahead/实验存储/HTML+可选 PDF 报告/CLI/replay/子进程 sandbox worker/C++ parallel engine batch sweep。
- M5：FastAPI UI-API v2；SQLite 任务队列、协作取消、崩溃恢复、WebSocket、Bearer/Host/Origin/no-CORS、GZip；`qc serve` 同源托管 UI；本地 toast/桌面通知。
- M6：React 19 + Vite 八页（行情/选股/策略/回测/实验/研究/模拟/数据 + 设置）；ECharts 图表、Monaco 本地打包、交易解释、onboarding、浅/深色、密度、移动端；Playwright **18** 条通过（含 paper/多策略组合/稳健性/插件）。
- M7：因子 IC/RankIC/ICIR、分层、衰减；参数扫描 + Sharpe 热力图；滚动验证；行业 FIFO 归因；Deflated Sharpe/PBO、成本敏感性、block bootstrap Monte Carlo、容量估计（近似口径）。
- M9：完成——虚拟账户/回放/委托撤单/成交/T+1/费用/信号 CSV/提醒/JSON 持久化/本地插件/只读多策略组合/服务端模拟时钟连续推进；真实 vendor 实时 feed 未捆绑。
- M8：完成——证券资料/PIT/ETF+可转债/合成分钟线/V2 dataset catalog；C++ 回测仍按 board 手数。
- M10：wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS/Windows zip（Windows 包由 `windows-latest` CI 构建）；无签名/公证，未做安装运行验证。
- 仓库：https://github.com/feiiiiii5/QuantCore （Apache-2.0）；申请季工作区未修改。

## 已验证开发环境
- macOS arm64；项目 `.venv` 为 **Python 3.12**（uv 管理）；系统 `python3` 可能是 3.11，项目命令一律 `uv run ...`。
- `uv 0.13.6`、Node `v23.11.0`、pnpm `12.14.0`、CMake `4.4.2`、Ninja `1.13.0`。
- Playwright E2E 需本机 **Chrome**（system Chrome channel）；Electron smoke 需 `desktop` 依赖，若环境设置 `ELECTRON_RUN_AS_NODE=1` 则用 `env -u ELECTRON_RUN_AS_NODE ...` 启动。

## 常用门禁与当前基线
```bash
uv run pytest                                      # 240 collected / 238 passed / 2 skipped
ctest --test-dir build/cmake --output-on-failure   # 95/95
pnpm -C ui test                                    # UI vitest 10 passed（5 files）
make lint                                          # ruff check/format + mypy 91 files 全绿
make verify-cpp                                    # C++ backend、差分 6/6、性能门禁（ratio 165x）
make e2e                                           # UI 构建 + 隔离 qc serve + Playwright 18/18（需 Chrome）
make doctor                                        # 只读环境自检（本机 pass=13 warn=0 fail=0 skip=1）
make demo                                          # 一条命令合成数据→快照→回测（约 2–3s，engine=cpp）
make test-quick                                    # 快速回归（排除 e2e/bench/network）
make ci-local                                      # 本地完整门禁
```
- CI 最近 5 个 job 全绿：`test (macos-latest)`、`test (ubuntu-latest)`、`windows-smoke`、`ui`、`desktop-windows-package`；Playwright E2E 只在本地 `make e2e` 跑，不进 GitHub CI。
- `docs/features.json` **121/121** 表示功能门禁有代码+证据，不等于真实 vendor 行情/签名安装包已完成。

## 开发/提交流程
- Conventional Commits；只 stage 明确路径（禁止 `git add -A` / `git add .`）；push 前复跑相关门禁（至少 `make lint` + `make test`，UI 改动跑 `make e2e`，C++ 改动跑 `make verify-cpp`）。
- 不提交运行期数据：`data/`、`experiments/`、`dist/`、`ui/dist/`、`.venv/`、`node_modules/`、
  `*.qpanel`、`*.sqlite*`、`*.parquet`（均在 `.gitignore`；`tests/golden` 例外）。
- 文档/功能变化同步 `docs/features.json`、`docs/acceptance-report.md`、本文件与 README，不只改一处。

## 工作边界
- 仅研究与模拟：不实现真实下单/券商连接，`BrokerGateway` 默认禁用；不得把合成数据/回测结果写成真实市场结论。
- 网络默认关闭：Tushare/AKShare/mootdx 需显式网络权限与凭据；无 Token 时只用 Synthetic + 录制 fixture。
- 合成数据必须标 `SYNTHETIC`；凭据（Token 等）不得写入代码、日志、文档或提交。
- 规则/费率未核实处标 `TODO(verify)` 并记入 `docs/rules-sources.md`，未核实前不要写成已验证事实。

## 本地测试文档
- 本机测试/门禁与规模基准操作见 [docs/LOCAL-TESTING.md](LOCAL-TESTING.md)（与上节基线配合使用）。

## 本轮实际验证
```bash
cd /Users/fei/Desktop/QuantCore
make lint
# ruff check/format 通过；mypy 91 files 无问题

uv run pytest
# 240 collected；238 passed / 2 skipped（交接后新增 44 条）

pnpm -C ui test
# 10 passed (5 files)

pnpm -C ui build
# 通过；初始 JS 约 1.4 MB raw，Monaco 3.3 MB 按路由懒加载

make e2e
# 构建 UI + 隔离 qc serve + Playwright 18 passed：
# 行情/选股/回测/实验/数据/策略/设置/研究/稳健性/插件/模拟/组合/onboarding/暗色/移动端/性能

uv run python scripts/verify_cpp.py
# C++ backend、差分 6/6、open 0.22ms、20 factors 20.7ms、engine 2.8ms、ratio 165x

make doctor
# summary ok（pass=13 warn=0 fail=0 skip=1）engine=cpp

make demo
# engine_backend=cpp；snapshot/run/HTML 报告生成；1208 交易日

make bench-scale
# 默认 800 证券 × 1208 天：总墙钟 4.51s、峰值 RSS 1583 MiB、qpanel open 0.3ms
```

## 本轮修复/新增
- M9 模拟交易：虚拟账户/回放/委托撤单/成交/CSV/提醒/本地插件/多策略组合/模拟时钟。
- M7 稳健性：DSR/PBO/成本敏感性/Monte Carlo/容量、因子相关性、随机扫描。
- M3：基准比较（净值/超额/跟踪误差/IR）与目标权重风险限制。
- M8：证券资料扩展、PIT 财务视图。
- M4：可选 PDF（本地 Chrome）、子进程 strategy worker、C++ parallel engine sweep。
- M10：SBOM/pip-audit、release/perf gate、Electron dev shell（headless smoke 验证 UI 加载）。
- 测试（该轮）：pytest 196 collected/194 passed/2 skipped；UI vitest 7；Playwright 18（交接后基线已更新，见下节）。

## 交接后增量（2026-11-02 R2）
- 交接：迁移交接文档独有内容并入本文件与 README，文档已删除；ARCHITECTURE/RELEASE 漂移修正。
- 本地测试：`qc doctor`/`make doctor`、`qc demo`/`make demo`、`make test-quick`、`make verify-local`（`scripts/local_verify.sh`）、`make bench-scale`（`scripts/scale_bench.py`）、`docs/LOCAL-TESTING.md`。
- 自检 API/UI：`GET /api/doctor` + 设置页「本地自检」卡片（pass/warn/fail/skip + hint，只读离线）。
- 模拟交易：部分成交（日成交量参与率上限，默认 10%）、`partial` 状态、跨交易日续成、逐笔费用/持仓/T+1；旧 session JSON 兼容；`docs/paper-trading.md`。
- 测试：pytest 240 collected / 238 passed / 2 skipped（新增 44 条）；UI vitest 10；Playwright 18/18（修正订单状态中文映射后的断言）。

## 已知缺口
1. M9：真实 vendor 实时 feed 未接（当前是历史快照/服务端模拟时钟）；部分成交已按「日成交量参与率上限」近似实现（无盘口/排队/滑点），公司行为未实现；不得声称可实盘。
2. M8：分钟线是 SYNTHETIC 视图（由日线拆桶），C++ 引擎仍只做日线、无分钟级回测/撮合；C++ 回测仍按
   board 手数（ETF/可转债 paper 手数已实现，不能宣称完整回测规则）。
3. M10：unsigned macOS/Windows zip 可构建（Windows zip 由 CI `windows-latest` 构建），但无签名/公证/自动更新，未做 Windows 安装/运行验证；后端不随包捆绑（默认需本地 `qc serve` 或 `QC_DESKTOP_URL`）。
4. M2：Tushare live 路径仅进程内 fake Pro 契约测试，真实 Token/网络/限流/字段差异未验证；
   全市场 5500×20y 基准与 10k sweep 未测；默认规模（800 证券 × 1208 天）的耗时与峰值 RSS 已由 `make bench-scale` 实测（见 `docs/PERFORMANCE.md`），不构成全市场结论。
5. M7 口径：行业 FIFO 归因、DSR/PBO/成本敏感性/MC/容量均为研究近似。
6. 规则 TODO(verify) 仍需外部官方来源核实（ST 幅度、盘后固定价历史、新股/退市整理、分红个税、部分费率）。
7. `docs/features.json` **121/121**；功能门禁全 true，但上述限制意味着不得宣称生产级实盘/签名安装包已完成。

## 续跑方法
```bash
cd /Users/fei/Desktop/QuantCore
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
make setup
make doctor          # 环境自检（只读离线）
make demo            # 一键合成演示（数据/快照/回测/报告）
make ci-local
make e2e
make desktop-smoke   # 可选
uv run qc serve --port 8000 --open
```
