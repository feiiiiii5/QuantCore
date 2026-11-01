# 验收报告 — 对照任务书

> 状态：2026-11-02。M0–M3 核心完成，M5/M6 工作台接通，M7 基础研究能力与 M9 基础模拟交易完成；M8、M9 进阶与部分 M10 未实现。
> 本报告只写实际运行过的命令与结果。`docs/features.json` 为逐项真相源（当前 **100/117**）。

## 里程碑
| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 底座 | ✅ | `make setup`、wheel 构建、`engine_backend=cpp`；CI macOS/Ubuntu 绿 |
| M1 C++ 基础 | ✅ 除 neutralize | ctest 95/95；M1 内核/指标/线程/面板/差分；neutralize 未实现 |
| M2 数据中心 | ✅ 基本 | Synthetic/LocalFile/Tushare fixture/AKShare/mootdx；Parquet+DuckDB+SQLite；快照/质量/PIT 元数据 |
| M3 回测引擎 | ✅ | ctest 95/95；C++/参考差分 6/6；规则/费用/T+1/手数/涨跌停/停牌/trace/指标 |
| M4 SDK/CLI/策略 | 🟡 大部分 | DSL 17 用例/309 assertions；7 模板；lookahead/实验/HTML 报告/CLI/replay；C++ 并行 sweep/PDF 未做 |
| M5 服务层 | ✅ | FastAPI 契约、Bearer/Host/Origin/no-CORS、SQLite 任务队列、WebSocket、取消/崩溃恢复、GZip、本地通知 |
| M6 UI V1 | ✅ | 八页工作台接通真实 API；Playwright **15** 条；浅/深色、移动端、无横向溢出、性能预算 |
| M7 研究工具 | ✅ 大部分 | IC/RankIC/ICIR、分层、衰减、扫描、滚动、归因、DSR/PBO、成本敏感性、Monte Carlo、容量；因子相关/随机扫描未做 |
| M8 V2 数据 | ❌ | 未实现 |
| M9 V3 模拟交易 | 🟡 大部分 | 虚拟账户/逐日回放/委托撤单/成交/信号 CSV/提醒/本地插件；持续实时/多策略组合未做 |
| M10 发布 | 🟡 部分 | wheel + 静态 UI + 中文文档 + 许可；Electron/安装包/SBOM 未做 |

## 本轮实际门禁
```bash
make lint
# ruff check/format 通过；mypy 69 files 无问题

uv run pytest -q -p no:warnings
# 165 collected；163 passed / 2 skipped

pnpm -C ui test
# 7 passed (4 files)

pnpm -C ui build
# 通过；初始 index/charts/react 约 1.4 MB raw（charts 1.0 MB），编辑器按需加载

make e2e   # 需要本机 Chrome；会构建 UI、启动隔离 qc serve
# pytest e2e marker + vitest + Playwright
# 17 passed: 行情/选股/回测/实验/笔记/数据/策略/设置/研究/onboarding/暗色/性能/全局搜索/移动端

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
- [ ] features.json 全 true：**80/117**（未达完成定义）。
- [ ] M8/M9（进阶）/M10 完整：未实现（见下）。
- [ ] 真实 Tushare 数据跑通：无 Token，未验证。
- [ ] 5500×20y / 10000 组 sweep / 峰值 RSS：未测（verify-cpp 为小集）。

## 已知缺口（按优先级）
1. **M9 模拟交易进阶**：持续实时模拟、提醒、多策略组合、插件、部分成交/公司行为未实现；不得声称可实盘。
2. **M8 V2 数据**：创业板/科创板/北交所完整规则已按板块设计，但分钟线/ETF/可转债/个股资料扩展未实现。
3. **M7 进阶**：Deflated Sharpe/PBO、成本敏感性、bootstrap/Monte Carlo、容量估计未实现；当前归因按行业 FIFO 近似。
4. **M10 发布**：Electron、macOS/Windows 安装包、SBOM/审计、性能回归脚本未完成；Windows 未验证。
5. **M4/M1 边界**：C++ 并行 sweep、PDF 报告、sandbox worker、neutralize；基准比较/风险限额未完整实现。
6. **数据验证**：Tushare 真实网络、全市场 5500×20y 基准、峰值 RSS、覆盖率统计未做。
7. **规则 TODO(verify)**：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。

## 下一步
1. 补 M9 进阶（持续模拟/提醒/多组合/插件），保持无真实下单；再做 M8 V2 数据与 M10 打包。
2. 补 M8 分钟线、ETF/可转债、板块规则和 PIT 财务视图。
3. Electron/打包/SBOM/Windows CI，补全 M10。
4. 真实 Tushare 小样本验证；全市场基准与内存测量。
5. 逐项把 `features.json` 的剩余 false 清零后再宣称完整交付。
