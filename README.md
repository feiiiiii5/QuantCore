# QuantCore

> 本地 A 股量化研究与回测工作台：行情 → 选股 → 策略 → 回测 → 复盘 → 实验复现。
> **历史表现不代表未来，不构成投资建议；本项目仅用于研究与模拟交易，不含真实下单。**

QuantCore 是一个 local-first 的量化研究桌面/网页工作台：C++20 引擎负责计算与撮合，
Python 负责数据、策略与实验管理，React 负责交互。数据与策略保存在本机，下载后可离线研究。

## 设计要点

- **C++ 核心 `qcore`**：定点账本、`.qpanel` mmap 面板、滚动/截面内核与技术指标、回测引擎、绩效指标、并行参数搜索。
- **先正确后快**：每项优化配基准、差分测试、确定性测试；纯 Python 参考实现只放在 `tests/reference`。
- **可验证**：`make verify-cpp` 检查 `engine_backend=="cpp"`、C++/参考实现差分、性能门禁。
- **本地优先**：Parquet 权威数据 + DuckDB 查询 + SQLite 状态 + `.qpanel` 引擎输入；零云依赖、运行期零 CDN。
- **仅研究与模拟**：`BrokerGateway` 默认禁用；界面与报告带免责声明。

## 快速开始（合成数据，三步）

```bash
# 1) 安装（Python 3.12 + CMake/Ninja + Node/pnpm）
make setup

# 2) 生成合成数据并构建快照（SYNTHETIC，仅用于开发/演示）
uv run qc data update --provider synthetic --n-sec 200 --start 2020-01-02 --end 2024-12-31
uv run qc snapshot build

# 3) 跑一次回测（template 见 qc backtest run --help）
uv run qc backtest run --template dual_ma --start 2021-01-01 --end 2024-12-31
```

> 真实数据：`qc data update --provider tushare` 需要 `TUSHARE_TOKEN`（或系统钥匙串）；无 Token 时全部功能用合成数据 + 录制 fixture 验证。见 `docs/DEV-SETUP.md` 与 `docs/DATA-LICENSES.md`。

## 开发

```bash
make build        # 构建 C++ / Python 扩展
make test         # pytest + ctest
make bench        # C++/Python 基准
make verify-cpp   # C++ 后端、差分与性能门禁
make ci-local     # 本地完整门禁
```

## 文档

- [计划与里程碑](docs/PLAN.md) · [进度](docs/PROGRESS.md) · [决策](docs/DECISIONS.md)
- [回测语义](docs/engine-semantics.md) · [规则来源](docs/rules-sources.md) · [数据字典](docs/data-dictionary.md)
- [架构](docs/ARCHITECTURE.md) · [开发环境/镜像](docs/DEV-SETUP.md) · [策略手册](docs/strategy-guide.md)
- [API](docs/API.md) · [快速上手（中文）](docs/QUICKSTART.md) · [贡献](CONTRIBUTING.md)

## 当前状态（2026-11-01）

- C++ core：panel/kernels/expression/engine，ctest **95/95**；`make verify-cpp` 差分/基准通过。
- Python：pytest **93 passed / 2 skipped（共 95）**，ruff/mypy 全绿；合成数据→快照→.qpanel→C++ 回测→实验/HTML 报告 CLI 端到端可跑。
- UI：React 19 + Vite 六页壳，`pnpm build/test` 通过；M6 尚未接真实后端数据。
- 诚实状态：`docs/features.json` **63/117 passes**；M0–M3 完成，M4 大部分，M5/M6 部分，M7–M10 未实现。详见 [验收报告](docs/acceptance-report.md)。
- 仅研究与模拟；合成数据标 `SYNTHETIC`；真实 Tushare 需 Token，未在本次验证。

## 许可证

Apache-2.0。第三方依赖许可证见 `docs/DATA-LICENSES.md` 与 SBOM（M10）。
