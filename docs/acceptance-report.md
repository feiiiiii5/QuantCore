# 验收报告 — 对照任务书

> 状态：2026-11-01 会话收尾。M0–M3 全绿；M4 大部分、M5/M6 部分；M7–M10 未实现。
> 本报告只写已实际跑过的命令与结果；未达成项不美化。

## 里程碑
| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 底座 | ✅ | `make setup`、wheel 构建、`engine_backend=cpp` |
| M1 C++ 基础 | ✅ | ctest 95/95；M1 36 用例/5828 assertions；ASan/UBSan/TSan；36 项 bench |
| M2 数据中心 | ✅ 基本 | pytest：providers 14、data_store 11、snapshot_qpanel 8、synthetic 11；合成快照→.qpanel 端到端 |
| M3 回测引擎 | ✅ | ctest 95/95；差分 6 用例；引擎 300×965 月度调仓 2.6ms；`verify-cpp` 通过 |
| M4 SDK/CLI/策略 | 🟡 部分 | DSL 17 用例/309 assertions；7 模板；lookahead/实验/报告/CLI/replay；C++ 并行 sweep 未做 |
| M5 服务层 | 🟡 部分 | FastAPI 8 测试、SQLite 任务队列、安全；WebSocket/通知未做 |
| M6 UI | 🟡 壳 | React 19+Vite 六页/主题/API client/空态；`pnpm build`/`test` 通过；未接真实数据 |
| M7 研究工具 | ❌ | 未实现 |
| M8 V2 数据 | ❌ | 未实现 |
| M9 V3 模拟交易 | ❌ | 未实现 |
| M10 发布 | 🟡 部分 | wheel + UI 构建；Electron/安装包/SBOM 未做 |

## 硬性约束自查
- [x] C++20 核心路径：panel/kernels/engine/metrics/expr；生产回测走 `_qcore.Engine`。
- [x] `make verify-cpp`：`engine_backend=cpp`、差分 6/6、open 0.18ms、20 因子 24.7ms、引擎 2.6ms、C++/参考 179×。
- [x] 本地优先/运行期零 CDN：数据/策略本地；UI 无远程字体/资源。
- [x] 仅研究与模拟：无真实下单；`BrokerGateway` 未实现（默认禁用语义保留）。
- [x] 先正确后快：C++ 95 测试 + 差分 + 确定性 + 基准；参考实现只在 tests/reference。
- [x] 不编造：规则/费率 TODO(verify)；合成数据标 SYNTHETIC；无真实数据入库。
- [x] 大陆网络镜像/工具链文档：docs/DEV-SETUP.md。
- [ ] features.json 全 true：**62/117**（未达完成定义）。
- [ ] `make e2e`：仅有 UI vitest；Playwright e2e 未接。
- [ ] 真实 Tushare 数据跑通：无 Token，未验证。
- [ ] 5500×20y / 10000 组 sweep / 峰值 RSS：未测（verify-cpp 只跑 300×965 小集）。

## 已知缺口（详见 docs/PROGRESS.md）
1. 实验产物缺 equity/positions/orders/trades/trace Parquet 与完整 replay 产物一致性。
2. C++ 并行 sweep、全市场基准、峰值内存、Windows CI 未验证。
3. 规则 TODO(verify)：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。
4. Tushare 真实网络路径、RQData 未验证；AKShare/mootdx 仅 fake module 契约测试。
5. M6 页面未接后端；M7–M10 未实现；Electron 未做。
6. Python 包装层单次回测约 0.4s（临时 .qpanel 写盘），引擎本身 2.6ms；后续可复用已打开 Panel。
7. 代码覆盖率未统计（C++/Python 目标 85%/80%）。
8. `features.json` 中 M2-015(PIT view)、M3-014(基准对比)、M4-005(沙箱 worker)、M4-009(PDF) 因未完整实现保持 false。

## 下一步
M5/M6 接线、实验 Parquet、C++ 并行 sweep、M7 因子分析、规则核实、Windows CI、Electron/打包。
