# 验收报告 — 对照任务书

> 状态：2026-11-02（交接后增量轮）。M0–M9 功能门禁完成；M10 完成发布工具/审计/性能门禁/桌面壳/unsigned macOS+Windows 打包。真实 vendor 实时 feed、签名/公证与安装运行验证仍是文档化限制。
> 本轮新增：`qc doctor` 环境自检、`qc demo` 一键演示、`GET /api/doctor` + 设置页自检卡片、模拟交易部分成交（成交量参与率上限）、本地测试工具链（Makefile target + `docs/LOCAL-TESTING.md` + 规模基准）。
> 本报告只写实际运行过的命令与结果。`docs/features.json` 为逐项真相源（当前 **121/121**）。

> **交接记录（2026-11-02）**：上一会话留下的迁移交接文档（377 行）的独有内容已吸收进
> `docs/PROGRESS.md`（开发环境/门禁基线/提交流程/工作边界）与 `README.md` 文档索引，交接文件已删除；
> `docs/ARCHITECTURE.md` 与 `docs/RELEASE.md` 中与当前代码事实不符的历史表述（导航数量、子进程资源限制、
> Playwright 数量、Windows 验证状态）已修正。下列已知限制保持原文，未做弱化。

## 里程碑
| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 底座 | ✅ | `make setup`、wheel 构建、`engine_backend=cpp`；CI macOS/Ubuntu 全量 + Windows pure-Python smoke |
| M1 C++ 基础 | ✅ | ctest 95/95；roll/cross 内核（含 neutralize）/指标/线程/面板/差分 |
| M2 数据中心 | ✅ 基本 | Synthetic/LocalFile/Tushare fixture+live code path/AKShare/mootdx；Parquet+DuckDB+SQLite；快照/质量/PIT 财务；实时 Tushare 仅 fake Pro 单测，真实 Token 未验证 |
| M3 回测引擎 | ✅ | ctest 95/95；C++/参考差分 6/6；规则/费用/T+1/手数/涨跌停/停牌/trace/指标/风险限制/基准比较 |
| M4 SDK/CLI/策略 | ✅ 大部分 | DSL/模板/实验/HTML+可选 PDF/子进程 sandbox worker/C++ parallel sweep/CLI/replay |
| M5 服务层 | ✅ | FastAPI 契约、Bearer/Host/Origin/no-CORS、SQLite 任务队列、WebSocket、取消/崩溃恢复、GZip、本地通知 |
| M6 UI V1 | ✅ | 八页工作台接通真实 API；Playwright **18** 条；浅/深色、移动端、无横向溢出、性能预算、全局搜索、插件/模拟/组合视图 |
| M7 研究工具 | ✅ | IC/RankIC/ICIR、分层、衰减、因子相关、grid/random 扫描、滚动、归因、DSR/PBO、成本敏感性、Monte Carlo、容量 |
| M8 V2 数据 | ✅ 大部分 | 证券资料/PIT/ETF+可转债/合成分钟线/V2 数据集目录已做；C++ 回测仍按 board 手数，分钟线为 SYNTHETIC |
| M9 V3 模拟交易 | ✅ | 虚拟账户/逐日回放/委托撤单/成交（含按成交量参与率的部分成交）/信号 CSV/提醒/本地插件/只读多策略组合/服务端模拟时钟自动推进；真实实时 vendor feed 未捆绑 |
| M10 发布 | 🟡 大部分 | wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS zip + Windows zip（windows-latest CI 构建）；无签名/公证、未做安装运行验证 |

## 本轮实际门禁
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
- [x] 合成数据标 `SYNTHETIC`；Tushare 真实网络需 Token，未验证。
- [x] features.json 全 true：**121/121**（交接后新增 4 项均有测试/证据）。
- [x] M8 分钟线（SYNTHETIC）/V2 dataset catalog、M9 模拟时钟连续模拟已完成（限制见下）。
- [ ] 真实 Tushare 数据跑通：无 Token，未验证。
- [ ] 全市场 5500×20y / 10000 组 sweep：未测；默认规模（800 证券 × 1208 天）的耗时与峰值 RSS 已由 `make bench-scale` 实测（见 `docs/PERFORMANCE.md`），不外推为全市场结论。

## 已知缺口（按优先级）
1. **M9 限制**：真实 vendor 实时 feed 未接（当前为历史快照/模拟时钟）；部分成交已实现为「日成交量参与率上限」的近似（无盘口/排队/滑点模型），公司行为（分红送转对持仓的调整）仍未实现；不得声称可实盘。
2. **M8 限制**：分钟线为 SYNTHETIC 视图；C++ 回测仍按 board 手数（ETF/可转债 paper 手数已实现）。
3. **M7 口径**：归因仍为行业 FIFO 近似；DSR/PBO/成本/MC/容量为研究近似。
4. **M10 发布**：Electron dev shell、unsigned macOS/Windows zip 已完成；签名/公证、安装运行验证未做；SBOM/audit/perf gate 已完成。
5. **剩余边界**：真实 vendor 实时 feed、签名/公证安装包、Windows 安装运行验证。
6. **数据验证**：Tushare 真实网络、全市场 5500×20y 基准与覆盖率统计未做；默认规模（800×1208）的耗时/峰值 RSS 已实测（`make bench-scale`，见 `docs/PERFORMANCE.md`），不构成全市场结论。
7. **规则 TODO(verify)**：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。

## 下一步
1. 接入真实 vendor 实时 feed；做 macOS/Windows 签名、公证与安装运行验证。
2. 保持无真实下单与本地优先；每轮 make ci-local/e2e/verify-cpp 后再 push。
3. features.json 已全 true；仍保留“真实 vendor 实时 feed/签名安装包”作为文档化限制。
4. 全市场 5500×20y 基准与 10k sweep 仍未测；`uv run python scripts/scale_bench.py --n-sec 5500` 已可用（需 ≥16 GiB 空闲内存），实测后可回填 `docs/PERFORMANCE.md`。
5. Windows 包已在 CI 构建但未做安装运行验证。
