# 验收报告 — 对照任务书

> 状态：2026-11-02（产品/UI 重构轮 R3）。M0–M10 功能门禁完成且第一轮增量（交接轮 R2：qc doctor/demo、部分成交、本地测试工具链）保持全绿；R3 新增产品理念与设计系统、UI 全面重构、可选实时行情、真实 A 股数据源与数据体检、零基础引导与教程。真实 vendor 授权行情、签名/公证安装包仍是文档化限制。
> 本报告只写实际运行过的命令与结果。`docs/features.json` 为逐项真相源（当前 **128/128**）。

> **交接记录（2026-11-02）**：上一会话留下的迁移交接文档（377 行）的独有内容已吸收进
> `docs/PROGRESS.md`（开发环境/门禁基线/提交流程/工作边界）与 `README.md` 文档索引，交接文件已删除；
> `docs/ARCHITECTURE.md` 与 `docs/RELEASE.md` 中与当前代码事实不符的历史表述（导航数量、子进程资源限制、
> Playwright 数量、Windows 验证状态）已修正。下列已知限制保持原文，未做弱化。

## 里程碑
| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 底座 | ✅ | `make setup`、wheel 构建、`engine_backend=cpp`；CI macOS/Ubuntu 全量 + Windows pure-Python smoke |
| M1 C++ 基础 | ✅ | ctest 95/95；roll/cross 内核（含 neutralize）/指标/线程/面板/差分 |
| M2 数据中心 | ✅ 基本 | Synthetic/LocalFile/Tushare fixture+live code path/AKShare/mootdx + **Sina 公开真实数据源**（未 Token，全 universe/日线/近似复权）；Parquet+DuckDB+SQLite；快照/质量/PIT 财务；数据体检 API/CLI；真实 3 只样本 import→snapshot→integrity=ok→回测已跑通；Tushare 真实 Token 未验证 |
| M3 回测引擎 | ✅ | ctest 95/95；C++/参考差分 6/6；规则/费用/T+1/手数/涨跌停/停牌/trace/指标/风险限制/基准比较 |
| M4 SDK/CLI/策略 | ✅ 大部分 | DSL/模板/实验/HTML+可选 PDF/子进程 sandbox worker/C++ parallel sweep/CLI/replay |
| M5 服务层 | ✅ | FastAPI 契约、Bearer/Host/Origin/no-CORS、SQLite 任务队列、WebSocket、取消/崩溃恢复、GZip、本地通知；R3 增 live 行情 REST/WS、数据体检、onboarding/presets/watchlist API |
| M6 UI V1 | ✅ | R3 重构：/today 驾驶舱 + /market 实时优先行情 + 8 页重做（结论先行、三态、新手模式）；token 化设计系统与组件库；Playwright **19** 条；浅/深色、移动端、无横向溢出、真实回测任务、数据体检、命令面板 |
| M7 研究工具 | ✅ | IC/RankIC/ICIR、分层、衰减、因子相关、grid/random 扫描、滚动、归因、DSR/PBO、成本敏感性、Monte Carlo、容量 |
| M8 V2 数据 | ✅ 大部分 | 证券资料/PIT/ETF+可转债/合成分钟线/V2 数据集目录已做；C++ 回测仍按 board 手数，分钟线为 SYNTHETIC |
| M9 V3 模拟交易 | ✅ | 虚拟账户/逐日回放/委托撤单/成交（含按成交量参与率的部分成交）/信号 CSV/提醒/本地插件/只读多策略组合/服务端模拟时钟自动推进；R3 提供可选实时行情（公开网页源，展示用、无真实下单）；无授权 vendor 实时 feed |
| M10 发布 | 🟡 大部分 | wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS zip + Windows zip（windows-latest CI 构建）；无签名/公证、未做安装运行验证 |

## 重构轮门禁（R3）
```bash
make lint
# ruff check/format 通过；mypy 104 files 无问题

uv run pytest
# 321 collected；319 passed / 2 skipped

pnpm -C ui test
# 10 passed (5 files)；pnpm -C ui build 通过

make e2e   # 本机 Chrome；隔离 qc serve + 新 UI
# Playwright 19 passed（新路由 /today、真实回测任务、数据体检、命令面板、移动端等）

make verify-cpp
# ok：C++ backend、差分 6/6、性能门禁

# 真实数据链路（Sina 公开接口，QC_ALLOW_NETWORK=1，样本 3 只）
uv run qc data update --provider sina --codes 600000,000001,300750 --start 2024-01-01 --end 2026-10-31 --data-root /tmp/qc-real-v2/data
# quality_passed=true；2049 rows；0 warnings；0 quarantined
uv run qc snapshot build --data-root /tmp/qc-real-v2/data --snapshots-root /tmp/qc-real-v2/data/snapshots
# snapshot=snap_dd1cff47d13ae1e3；source=SINA；synthetic=false；qpanel=true
uv run qc data integrity --snapshots-root /tmp/qc-real-v2/data/snapshots
# status=ok；coverage=100.00%；accuracy={ohlc:0, volume_amount:0, limit:0, adjustment_breaks:0}
uv run qc backtest run --template dual_ma --snapshot <snap> --snapshots-root ... --start 2024-06-01 --end 2026-10-31
# engine_backend=cpp；snapshot source=SINA synthetic=false；总收益 83.54%、年化 28.82%、Sharpe 1.05、最大回撤 31.90%、55 笔交易（研究示例，不构成投资建议）
```

## 重构轮增量（R3）

- **产品理念与设计规范**：新增 `docs/PRODUCT.md`（市场观察、三条支柱：看得懂/跑得通/信得过、研究卡片/数据体检/行情→研究直连）与 `docs/DESIGN-SPEC.md`（IA、tokens、组件契约、逐页规格、新手模式、实时行情表现规则）。
- **UI 全面重构**：新增 `/today` 驾驶舱（市场状态带、自选、新手进度、最近研究、数据体检）与 `/market` 实时优先行情页；AppBar 实时指数条 + ⌘K 命令面板 + 新手模式开关；token 化设计系统（浅/深色、密度、红绿/绿红/色盲三套涨跌色）；17 个通用组件；8 个页面按「结论先行 + 三态 + 新手提示」重做。截图见 `docs/screenshots/`。
- **实时行情（可选联网）**：`GET /api/live/{status,indices,quotes}` + `WS /ws/live`；上海市场时钟、Eastmoney→Sina 双源与降级、限速缓存、离线/休市/异常显式状态；默认完全离线（`QC_ALLOW_NETWORK=1` 才联网），测试不联网（fixtures）。
- **真实数据与准确性**：新增 Sina 公开行情 provider（全 A 股 universe 5576 只、原始日线约 2000 根、volume 单位为股已实测；腾讯 qfq 推导复权/近似公司行为，并对 vendor 因子跳点做「持续性 + 涨跌停合理性」过滤）；新增数据体检（覆盖率/缺口/OHLC/量额/涨跌停/复权连续性/跨源抽样，默认离线）；`GET /api/data/integrity` + `qc data integrity`；质量门禁对少量坏行改为隔离并告警（不整批失败）。真实 3 只样本链路见上，integrity=ok 且 accuracy 全 0。
- **零基础引导**：`/api/onboarding` 4 步（data/backtest/result/data_health，自动检测 + 幂等完成）、6 个白话策略预设、`/api/watchlist`、首页新手清单 + 设置页新手模式；新增 `docs/TUTORIAL.md`（163 行零基础教程）。
- **测试**：pytest 321 collected / 319 passed / 2 skipped（R3 新增 live 11、sina 26、integrity 11、onboarding 16 等及 provider 回归测试）；Playwright 19/19（新 UI 重写选择器）；UI vitest 10。

## 交接后增量轮门禁（R2，历史记录）
```bash
make lint
# ruff check/format 通过；mypy 91 files 无问题

uv run pytest
# 240 collected；238 passed / 2 skipped

pnpm -C ui test
# 10 passed (5 files)

pnpm -C ui build
# 通过（tsc + vite；仅有既有 chunk-size 提示）

make e2e   # 需要本机 Chrome；会构建 UI、启动隔离 qc serve
# Playwright 18 passed（含设置页自检、模拟交易部分成交后的状态断言）

make verify-cpp
# ok：C++ backend、差分 6/6、open 0.22ms、20 factors 20.7ms、engine 2.8ms、ratio 165x

make doctor
# summary ok（pass=13 warn=0 fail=0 skip=1）engine=cpp

make demo
# engine_backend=cpp；snapshot/run/HTML 报告生成；1208 交易日；SYNTHETIC

make bench-scale
# 默认 800 证券：总墙钟 4.51s、峰值 RSS 1583 MiB、qpanel open 0.3ms（详见 docs/PERFORMANCE.md）
```

## 本轮增量（交接后）

- **交接完成**：迁移交接文档的独有内容已并入 `docs/PROGRESS.md`/`README.md`，交接文件已删除；`ARCHITECTURE`/`RELEASE` 漂移已修正（见上方交接记录）。
- **本地自检**：`qc doctor` / `GET /api/doctor` / 设置页「本地自检」卡片——只读离线检查 Python/.venv、C++ 引擎、数据仓库、快照、UI 构建、Node/pnpm、端口、磁盘、Git、Chrome、C++ 测试二进制；输出 pass/warn/fail/skip 与修复提示；`--strict` 可作脚本门禁。
- **一键演示**：`qc demo` / `make demo`——SYNTHETIC 面板 → Parquet → 不可变快照 → C++ 回测 → HTML 报告，默认写入 `data/demo/` 与 `experiments/<run_id>/`（均 gitignore），约 2–3s。
- **本地测试工具链**：`make doctor/demo/test-quick/verify-local/bench-scale`、`scripts/local_verify.sh`（分段耗时 + PASS/FAIL）、`scripts/scale_bench.py`（面板/Parquet/.qpanel/engine/峰值 RSS）、`docs/LOCAL-TESTING.md`（命令矩阵 + 隔离方式 + 故障排查）。
- **模拟交易部分成交**：按日成交量参与率上限（默认 10%）分笔成交，新增 `partial` 状态、跨交易日续成、逐笔费用/持仓/T+1 正确；旧 session JSON 向后兼容；语义见 `docs/paper-trading.md`。
- **测试**：pytest 240 collected / 238 passed / 2 skipped（新增 44 条：doctor 20、demo 9、api doctor 4、paper partial 10、paper api 1）；Playwright 18/18（修正订单状态中文映射后的断言）；UI vitest 10。

## 硬性约束自查
- [x] C++20 核心路径：panel/kernels/engine/metrics/expr；生产回测走 `_qcore.Engine`。
- [x] 本地优先/运行期零 CDN：数据、策略、Monaco、ECharts 均本地打包；UI 无远程字体/资源。
- [x] 同源部署：`qc serve` 同时提供 `/api` 与 `ui/dist`；Vite dev 使用 `/api` `/ws` `/health` 代理到 8000。
- [x] 仅研究与模拟：无真实下单；`BrokerGateway` 未实现；界面与报告有“不构成投资建议”。
- [x] 认证：Bearer token、Host/Origin 校验、无 CORS、loopback only；token 从 `qc serve --open` URL 持久化后立即从地址栏移除。
- [x] 合成数据标 `SYNTHETIC`；真实 A 股数据可经 Sina 公开接口导入（`QC_ALLOW_NETWORK=1`，非商用、不得再分发），Tushare 真实网络需 Token，未验证。
- [x] features.json 全 true：**128/128**（R3 新增 7 项：Sina provider、数据体检、实时行情、onboarding/watchlist、产品理念/设计系统、页面重构、零基础教程，均有测试或实测证据）。
- [x] 网络默认关闭：实时行情与真实数据导入均需显式 `QC_ALLOW_NETWORK=1`；测试只走录制 fixtures，不联网。
- [x] 真实数据准确性实测（2026-11-02）：Sina 3 只样本 2049 根日线，质量门禁 passed、0 告警、0 隔离行；`qc data integrity` status=ok、coverage=100%、accuracy 全 0；真实快照上 C++ 回测成功（synthetic=false/source=SINA）。
- [x] 实时行情：REST/WS、双源降级、市场时钟、离线/休市/异常显式状态；仅展示用途，不参与下单。
- [x] M8 分钟线（SYNTHETIC）/V2 dataset catalog、M9 模拟时钟连续模拟已完成（限制见下）。
- [ ] 真实 Tushare 数据跑通：无 Token，未验证（Sina 公开接口已跑通，作为替代真实源）。
- [ ] 全市场 5500×20y / 10000 组 sweep：未测；默认规模（800 证券 × 1208 天）的耗时与峰值 RSS 已由 `make bench-scale` 实测（见 `docs/PERFORMANCE.md`），不外推为全市场结论。

## 已知缺口（按优先级）
1. **行情/交易限制**：实时行情来自公开网页接口（Sina/Eastmoney，未授权、无 SLA，约 3 秒轮询、无 L2/盘口），仅展示；模拟交易部分成交为「日成交量参与率上限」近似（无排队/滑点），公司行为（分红送转对持仓的调整）仍未实现；不得声称可实盘。
2. **真实数据限制**：Sina 公开接口非官方、约 2000 根日线（约 2018 年起）；无真实成交额（按 OHLC×volume 估算，已标注）；复权/公司行为由腾讯 qfq 近似推导（`SINA_APPROX`，已过滤 vendor 跳点，但仍是近似）；全市场导入（5576 只）实测约 30–45 分钟，本轮只端到端验证了 3 只样本；Eastmoney 端点在本机网络被限流；Tushare 真实 Token 未验证。
3. **M8 限制**：分钟线为 SYNTHETIC 视图；C++ 回测仍按 board 手数（ETF/可转债 paper 手数已实现）。
4. **M7 口径**：归因仍为行业 FIFO 近似；DSR/PBO/成本/MC/容量为研究近似。
5. **M10 发布**：Electron dev shell、unsigned macOS/Windows zip 已完成；签名/公证、安装运行验证未做；SBOM/audit/perf gate 已完成。
6. **性能验证**：全市场 5500×20y 基准与 10k sweep 未测；默认规模（800×1208）已实测（`make bench-scale`），不构成全市场结论。
7. **规则 TODO(verify)**：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。

## 下一步
1. 做 macOS/Windows 签名、公证与安装运行验证；若要商用实时行情，接入授权 vendor feed（替换公开网页源）。
2. 全市场真实数据端到端验证（5576 只 × 20y）：导入→体检→快照→回测，并把覆盖率/耗时回填 `docs/PERFORMANCE.md`；`uv run python scripts/scale_bench.py --n-sec 5500` 已可用（需 ≥16 GiB 空闲内存）。
3. 真实数据准确性继续加固：成交额获取（替代估算）、公司行为与除权参考价核验、更多样本与跨源抽样（需网络时开启）。
4. 保持无真实下单与本地优先；每轮 make ci-local/e2e/verify-cpp 后再 push；features.json 全 true，“授权实时 feed/签名安装包”作为文档化限制。
5. Windows 包已在 CI 构建但未做安装运行验证。
