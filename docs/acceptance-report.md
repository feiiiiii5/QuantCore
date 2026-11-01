# 验收报告 — 对照任务书

> 状态：2026-11-02。M0–M7 基本完成，M9 大部分完成；M8 仅完成证券资料扩展，M10 完成发布工具/审计/性能门禁但未做 Electron/安装包。
> 本报告只写实际运行过的命令与结果。`docs/features.json` 为逐项真相源（当前 **110/117**）。

## 里程碑
| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 底座 | ✅ | `make setup`、wheel 构建、`engine_backend=cpp`；CI macOS/Ubuntu 绿 |
| M1 C++ 基础 | ✅ | ctest 95/95；roll/cross 内核（含 neutralize）/指标/线程/面板/差分 |
| M2 数据中心 | ✅ 基本 | Synthetic/LocalFile/Tushare fixture/AKShare/mootdx；Parquet+DuckDB+SQLite；快照/质量/PIT 财务视图；实时 Tushare 未验证 |
| M3 回测引擎 | ✅ | ctest 95/95；C++/参考差分 6/6；规则/费用/T+1/手数/涨跌停/停牌/trace/指标/风险限制/基准比较 |
| M4 SDK/CLI/策略 | ✅ 大部分 | DSL/模板/实验/HTML+可选 PDF/子进程 sandbox worker/C++ parallel sweep/CLI/replay |
| M5 服务层 | ✅ | FastAPI 契约、Bearer/Host/Origin/no-CORS、SQLite 任务队列、WebSocket、取消/崩溃恢复、GZip、本地通知 |
| M6 UI V1 | ✅ | 八页工作台接通真实 API；Playwright **18** 条；浅/深色、移动端、无横向溢出、性能预算、全局搜索、插件/模拟/组合视图 |
| M7 研究工具 | ✅ | IC/RankIC/ICIR、分层、衰减、因子相关、grid/random 扫描、滚动、归因、DSR/PBO、成本敏感性、Monte Carlo、容量 |
| M8 V2 数据 | 🟡 部分 | 证券资料/PIT 财务已扩展；分钟线/ETF/可转债/V2 datasets 未做 |
| M9 V3 模拟交易 | 🟡 大部分 | 虚拟账户/逐日回放/委托撤单/成交/信号 CSV/提醒/本地插件/只读多策略组合/服务端模拟时钟自动推进；真实实时行情 feed 未接 |
| M10 发布 | 🟡 大部分 | wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS app zip；Windows 包未在 Windows 验证、无签名/公证 |

## 本轮实际门禁
```bash
make lint
# ruff check/format 通过；mypy 69 files 无问题

uv run pytest -q -p no:warnings
# 187 collected；185 passed / 2 skipped

pnpm -C ui test
# 7 passed (4 files)

pnpm -C ui build
# 通过；初始 index/charts/react 约 1.4 MB raw（charts 1.0 MB），编辑器按需加载

make e2e   # 需要本机 Chrome；会构建 UI、启动隔离 qc serve
# pytest e2e marker + vitest + Playwright
# 18 passed: 行情/选股/回测/实验/笔记/数据/策略/设置/研究/onboarding/暗色/性能/全局搜索/移动端

make verify-cpp
# C++ backend、差分 6/6、open/20 factors/engine/ratio 门禁通过
```

## 硬性约束自查
- [x] C++20 核心路径：panel/kernels/engine/metrics/expr；生产回测走 `_qcore.Engine`。
- [x] 本地优先/运行期零 CDN：数据、策略、Monaco、ECharts 均本地打包；UI 无远程字体/资源。
- [x] 同源部署：`qc serve` 同时提供 `/api` 与 `ui/dist`；Vite dev 使用 `/api` `/ws` `/health` 代理到 8000。
- [x] 仅研究与模拟：无真实下单；`BrokerGateway` 未实现；界面与报告有“不构成投资建议”。
- [x] 认证：Bearer token、Host/Origin 校验、无 CORS、loopback only；token 从 `qc serve --open` URL 持久化后立即从地址栏移除。
- [x] 合成数据标 `SYNTHETIC`；Tushare 真实网络需 Token，未验证。
- [ ] features.json 全 true：**109/117**（未达完成定义）。
- [ ] M8 V2 数据、M9 实时行情、M10 Electron/安装包：未完成（见下）。
- [ ] 真实 Tushare 数据跑通：无 Token，未验证。
- [ ] 5500×20y / 10000 组 sweep / 峰值 RSS：未测（verify-cpp 为小集）。

## 已知缺口（按优先级）
1. **M9 实时行情与进阶**：真实实时 feed 未接（当前为历史快照/模拟时钟）；无部分成交/公司行为；不得声称可实盘。
2. **M8 V2 数据**：证券资料/PIT 财务已扩展；分钟线/ETF/可转债/V2 datasets 未实现。
3. **M7 口径**：归因仍为行业 FIFO 近似；DSR/PBO/成本/MC/容量为研究近似。
4. **M10 发布**：Electron dev shell 已完成；macOS/Windows 安装包未做；Windows 未验证；SBOM/audit/perf gate 已完成。
5. **剩余边界**：M0 Windows CI、M2 实时 Tushare、M8 数据扩展、M10 安装包。
6. **数据验证**：Tushare 真实网络、全市场 5500×20y 基准、峰值 RSS、覆盖率统计未做。
7. **规则 TODO(verify)**：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。

## 下一步
1. 补 M8 V2 数据与 M10 Electron/安装包；真实 Tushare 小样本验证。
2. 保持无真实下单与本地优先；每轮 make ci-local/e2e/verify-cpp 后再 push。
3. 剩余 8 项 features.json 清零后再宣称完整交付。
4. 全市场 5500×20y 基准、10k sweep、峰值 RSS 仍未测。
5. Windows CI/打包仍未验证。
