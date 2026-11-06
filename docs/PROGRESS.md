# PROGRESS — 当前进度

> 每阶段结束记录：完成项、验证命令与结果、已知缺口、下一步、续跑方法。上下文清空后据此恢复。
> 更新时间：2026-11-06。
> 交接记录（2026-11-02）：上一会话交接文档的独有信息已并入本文件，交接文件已删除；续跑以本文件为准。

## 2026-11-06：研究证据与账户正确性优化

- 空表往返：两条实验保存路径都写入空财务/公司行为表，保留列与类型，避免同一数据经派生后指纹变化；已遗失结构的旧文件不猜测补齐。
- 自动评审补充：离开 `?source=` 时清除来源数据选择与恢复标记，保留普通快照选择；修复前真实浏览器复现普通回测错误携带来源实验。
- 实验比较从原始资金金额改为按记录初始资金归一的净值，补充回撤、参照实验差值、13 项条件核对和来源记录。保留旧 API 字段；缺失记录显示未知，不制造可比性。
- `source_run_id` 沿用原实验快照或已保存面板、完整费用/规则和策略条件，新实验保存父记录；支持局部费用修改，原记录不变。UI「沿用数据与参数」与「继续研究」已接通。
- 修复月收益遗漏跨月首日、回撤忽略初始资金且二次复杂度、任务错误帧忽略终态、worker 关闭超时丢失线程及领取/关闭竞争。
- 修复模拟账户保存重开丢失成本精度、不同起始日期组合权重漂移；切换账户停止本地播放并忽略旧请求返回。修复切换证券沿用旧报价、WS 断流后不再 HTTP 刷新。
- 页面按需加载，共享运行时代码不再拖入 Monaco；工程规则改为按影响选择必要验证，不重复执行已经完成的建设阶段。
- 已验证：Python **373 passed / 2 skipped**；ruff lint/format 与 mypy（106 源文件）通过；UI **19/19**；既有真实服务 E2E **18/18**；C++ 差分 **6/6**，300×965 合成规模引擎约 2.79ms、20 因子约 24ms。上述数字是本机检查，不代表全市场或实盘能力。
- 本机 Node 26 的原生 Web Storage 与现有 jsdom 测试环境冲突，UI 测试使用 `NODE_OPTIONS=--no-experimental-webstorage`；依赖版本与哈希未更新。随后 GitHub Ubuntu 安装在清华镜像的 `httptools` Linux wheel 返回 403；已将锁内安装包地址改为 PyPI 官方文件源，保留镜像索引、依赖图、版本和全部哈希，消除区域镜像文件地址依赖。

## 当前状态
- R5：研究条件可比性、数据复用/来源链、账户与行情身份、收益口径和 worker 生命周期优化已完成；具体增量证据见上节。
- M0：完成。`make setup/test`、wheel、macOS/Ubuntu 全量 CI + Windows pure-Python smoke；C++ Windows 未支持。
- M1：C++ types/calendar/tpool/.qpanel/内核/指标/零拷贝绑定；ctest 95/95；cross-sectional neutralize 已实现并绑定。
- M2：Synthetic/LocalFile/Tushare(fixture+live API 代码路径)/AKShare/mootdx + **Sina 公开真实数据源**；摄取/质量/快照(内容寻址+PIT 元数据)/Parquet+DuckDB+SQLite；PIT 财务视图；**数据体检**(覆盖率/缺口/OHLC/量额/涨跌停/复权/跨源)；真实 Sina 3 只样本 import→snapshot→integrity=ok→C++ 回测已跑通；真实 Tushare Token 未验证。
- M3：event-driven 引擎，规则/费用/T+1/手数/涨跌停/停牌/除权除息/trace/指标；差分 6/6；风险限制/基准比较；引擎 300×965 月度调仓约 2.6ms。
- M4：DSL/7 模板/lookahead/实验存储/HTML+可选 PDF 报告/CLI/replay/子进程 sandbox worker/C++ parallel engine batch sweep。
- M5：FastAPI UI-API v2；SQLite 任务队列、协作取消、崩溃恢复、WebSocket、Bearer/Host/Origin/no-CORS、GZip；`qc serve` 同源托管 UI；本地 toast/桌面通知；R3 增 live 行情 REST/WS、数据体检、onboarding/presets/watchlist API；R4 真实 XSHG 交易日历（exchange-calendars）、live/provider 正确性修复、UI 共享 WS 消费。
- M6：R4 重构——Apple HIG 设计系统 v2（毛玻璃/34px 标题/8pt 网格/克制动效），Radix UI + framer-motion + sonner + cmdk + vaul + lightweight-charts（移除 echarts，初始 JS 1.09MB→0.60MB），10 页重写；Playwright **18** 条、ui-audit 10 路由 0 console/0 溢出；R3 的 /today、/market、结论先行与新手模式保留。
- M7：因子 IC/RankIC/ICIR、分层、衰减；参数扫描 + Sharpe 热力图；滚动验证；行业 FIFO 归因；Deflated Sharpe/PBO、成本敏感性、block bootstrap Monte Carlo、容量估计（近似口径）。
- M9：完成——虚拟账户/回放/委托撤单/成交/T+1/费用/信号 CSV/提醒/JSON 持久化/本地插件/只读多策略组合/服务端模拟时钟连续推进；R3 提供可选实时行情（公开网页源、仅展示），无授权 vendor feed、无真实下单。
- M8：完成——证券资料/PIT/ETF+可转债/合成分钟线/V2 dataset catalog；C++ 回测仍按 board 手数。
- M10：wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS/Windows zip（Windows 包由 `windows-latest` CI 构建）；无签名/公证，未做安装运行验证。
- 仓库：https://github.com/feiiiiii5/QuantCore （Apache-2.0）；申请季工作区未修改。

## 已验证开发环境
- macOS arm64；项目 `.venv` 为 **Python 3.12**（uv 管理）；系统 `python3` 可能是 3.11，项目命令一律 `uv run ...`。
- `uv 0.13.6`、Node `v23.11.0`、pnpm `12.14.0`、CMake `4.4.2`、Ninja `1.13.0`。
- Playwright E2E 需本机 **Chrome**（system Chrome channel）；Electron smoke 需 `desktop` 依赖，若环境设置 `ELECTRON_RUN_AS_NODE=1` 则用 `env -u ELECTRON_RUN_AS_NODE ...` 启动。

## 常用门禁与当前基线
```bash
uv run pytest                                      # 354 collected / 352 passed / 2 skipped
ctest --test-dir build/cmake --output-on-failure   # 95/95
pnpm -C ui test                                    # UI vitest 10 passed（5 files）
make lint                                          # ruff check/format + mypy 105 files 全绿
make verify-cpp                                    # C++ backend、差分 6/6、性能门禁（ratio 165x）
make e2e                                           # UI 构建 + 隔离 qc serve + Playwright 18/18（需 Chrome）
make doctor                                        # 只读环境自检（本机 pass=13 warn=0 fail=0 skip=1）
make demo                                          # 一条命令合成数据→快照→回测（约 2–3s，engine=cpp）
make test-quick                                    # 快速回归（排除 e2e/bench/network）
make ci-local                                      # 本地完整门禁
```
- CI 最近 5 个 job 全绿：`test (macos-latest)`、`test (ubuntu-latest)`、`windows-smoke`、`ui`、`desktop-windows-package`；Playwright E2E 只在本地 `make e2e` 跑，不进 GitHub CI。
- `docs/features.json` **134/134** 表示功能门禁有代码+证据，不等于授权实时行情/全市场真实数据/签名安装包已完成。

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

## 重构轮增量（2026-11-02 R3：产品/UI/实时/真实数据/零基础）
- 产品与设计：新增 `docs/PRODUCT.md`（理念/三支柱/创新点/市场与来源）与 `docs/DESIGN-SPEC.md`（IA、tokens、组件契约、逐页规格、新手模式、实时状态）。
- UI 重构：`/today` 驾驶舱（市场状态带/自选/新手进度/最近研究/数据体检）、`/market` 实时优先行情；AppBar 实时指数条 + ⌘K 命令面板 + 新手模式；三套涨跌配色（红绿/绿红/色盲）、明暗主题、密度；11 个页面按统一体例重做；截图在 `docs/screenshots/`。
- 实时行情（可选联网）：`/api/live/{status,indices,quotes}` + `WS /ws/live`；上海市场时钟、Eastmoney→Sina 双源降级、限速缓存、离线/休市/异常显式状态；默认完全离线，`QC_ALLOW_NETWORK=1` 才联网，测试走 fixtures。
- 真实数据与准确性：Sina 公开 provider（全 A 股 5576 只 universe、约 2000 根日线、volume=股已实测、腾讯 qfq 近似复权并过滤 vendor 跳点）；数据体检 API/CLI；质量门禁把少量坏行隔离为告警而非整批失败。真实 3 只样本（600000/000001/300750，2024-01-01..2026-10-31，2049 根）质量 passed、0 隔离、integrity=ok、accuracy 全 0，并在真实快照上跑通 C++ 回测。
- 零基础引导：`/api/onboarding` 4 步自动检测、6 个白话预设、`/api/watchlist`、首页新手清单、设置页新手模式；新增 `docs/TUTORIAL.md`（163 行零基础教程）。
- 测试：pytest 321 collected / 319 passed / 2 skipped；Playwright 19/19；UI vitest 10；`make lint` / `make verify-cpp` / `make doctor` / `make demo` 全绿。

## 成熟方案重构轮（2026-11-02 R4：Apple 设计语言 + GitHub 成熟库）
- 设计系统 v2：`docs/DESIGN-SPEC.md` 重写为 Apple HIG 落地规范；`ui/src/styles/**` 全量重写（tokens/base/layout/components/business/overlays/views，删除 legacy），16 个新原语；毛玻璃 AppBar/StatusBar/Rail、34px 大标题、8pt 网格、hairline、reduced-motion、focus-visible。
- 成熟开源栈：@radix-ui/react-*、framer-motion、sonner、cmdk、vaul、lightweight-charts（统一图表并移除 echarts）、TanStack Table/Virtual/Query、lucide-react；10 页重写为 Apple 风格（今日/行情/回测/数据/模拟/研究/选股/策略/实验/设置）。
- 真实交易日历：`trading_calendar.py`（exchange-calendars XSHG）替换 `realtime/clock.py` 的星期几启发式；2024 春节/国庆、跨节假日 next_open、节后 last_trade_date 均有离线测试。
- 实时正确性修复：920xxx 北交所映射、盘前误标停牌、非自选股报价不刷新、异常路径、闭市轮询 3s→15s、东财 turnover、qfq/raw 去重、Sina 时区、并发钳制；provider→quality 集成回归。
- UI 实时链路：`lib/liveStream.ts` 共享 WebSocket（每代码集一个连接、退避重连、写 react-query 缓存），失败回退 15s 轮询；真实网络 + WS 帧已验证。
- 前端工程：Vite dev proxy 重写 Origin（修复 dev 403）、manualChunks、`ui/scripts/ui-audit.mjs` 审计脚本；tsc/vitest/build 全绿。
- 验证：pytest 352 passed/2 skipped、ctest 95/95、Playwright 18/18、vitest 10、ruff/mypy 105 files；真实联网行情 /api/live/status=live + WS 帧（浦发 10.14 / 平安 11.58 + 4 指数）。

## 已知缺口
1. M9：实时行情来自公开网页接口（未授权、约 3 秒轮询、无 L2），仅展示；UI 已用共享 WS 消费，但数据源本身仍非授权 feed；部分成交按「日成交量参与率上限」近似（无盘口/排队/滑点），公司行为未实现；不得声称可实盘。
2. M8：分钟线是 SYNTHETIC 视图（由日线拆桶），C++ 引擎仍只做日线、无分钟级回测/撮合；C++ 回测仍按
   board 手数（ETF/可转债 paper 手数已实现，不能宣称完整回测规则）。
3. M10：unsigned macOS/Windows zip 可构建（Windows zip 由 CI `windows-latest` 构建），但无签名/公证/自动更新，未做 Windows 安装/运行验证；后端不随包捆绑（默认需本地 `qc serve` 或 `QC_DESKTOP_URL`）。
4. M2：Sina 公开接口非官方，约 2000 根日线、成交额按 OHLC×volume 估算、复权/公司行为为近似（`SINA_APPROX`）；全市场 5576 只导入未端到端验证（估算 30–45 分钟），本轮只验证 3 只样本；Eastmoney 在本机网络被限流；Tushare live 路径仅 fake Pro 契约测试，真实 Token 未验证；全市场 5500×20y 基准与 10k sweep 未测，默认规模（800×1208）已实测（见 `docs/PERFORMANCE.md`），不构成全市场结论。
   exchange-calendars XSHG 数据到 2026-12-31，之后回退星期几；增量 ingest 不重算历史 adj_factor（分红季建议全量重建）；qfq 跳点过滤存在末端/大送转/20% 判板边界（详见 `docs/AUDIT-R3.md`）。
5. M7 口径：行业 FIFO 归因、DSR/PBO/成本敏感性/MC/容量均为研究近似。
6. 规则 TODO(verify) 仍需外部官方来源核实（ST 幅度、盘后固定价历史、新股/退市整理、分红个税、部分费率）。
7. `docs/features.json` **134/134**；功能门禁全 true，但上述限制意味着不得宣称授权实时行情/全市场真实数据/生产级实盘/签名安装包已完成。

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

# 可选：联网实时行情 + 真实数据导入（默认关闭）
QC_ALLOW_NETWORK=1 uv run qc serve --port 8000 --open
QC_ALLOW_NETWORK=1 uv run qc data update --provider sina --codes 600000,000001,300750 \
  --start 2024-01-01 --end 2026-10-31 --data-root data
uv run qc snapshot build --data-root data --snapshots-root data/snapshots
uv run qc data integrity --snapshots-root data/snapshots

# 前端开发（Vite proxy 已重写 Origin，可直接使用）
pnpm -C ui dev                  # 另开 qc serve --port 8000
node ui/scripts/ui-audit.mjs    # QC_BASE/QC_TOKEN：截图 + overflow/console/a11y 审计
```
