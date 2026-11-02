# PERFORMANCE — 基准方法与门禁

## 环境（开发机）
- Apple M2 Pro（10 核，16GB），macOS 27.2，Apple clang 21，Release `-O3 -DNDEBUG`；无 `-march=native`。
- CI 小集：GitHub Actions macOS/Ubuntu；nightly 全量。

## 基准集
- 确定性合成全市场：约 5500 证券 × 20 年日线（含掩码），固定 seed，可复现；CI 用小集。
- 报告机器、编译器、flags、commit、数据集 hash；取 5 次中位数；报告 p50/p99。

## 初始门禁（§10）
| 项 | 目标 |
|---|---|
| 打开快照 mmap | < 200ms |
| 20 个常见因子全面板（8 线程） | < 3s |
| 单次回测（月度调仓/前 50/10 年/完整规则/trace=summary） | < 1s |
| 10000 组参数（8 核） | < 5min |
| 1→N 线程结果 | 逐位一致 |
| 峰值内存（全市场 20 字段） | < 4GB |
| C++ vs Python 参考 | ≥50× |
| CI 基线回归 | >10% 失败 |

实测结果写入本节下方并附提交/日期；未实测前不写数字。

## 实测（2026-11-01，Apple M2 Pro / macOS 27.2 / Apple clang 21 / Release）

数据：`scripts/verify_cpp.py` 的确定性 SYNTHETIC 面板，300 证券 × 965 交易日（300×965，17 个 double 字段），
月度调仓、前 10 等权、trace=summary；20 个因子 = 10 个 rolling_panel + 10 个 cross_panel，8 Python 线程
（C++ 内核释放 GIL）。

| 项 | 实测 | 初始门禁 | 结论 |
|---|---:|---:|---|
| Panel.open 快速路径 | 0.20 ms | <200 ms | 通过 |
| 20 因子全面板（8 线程） | 21.5 ms | <3000 ms | 通过（小集；全市场 nightly） |
| 单次回测（直接 C++ Engine.run） | 2.6 ms | <1000 ms | 通过 |
| 单次回测（含 Python 包装：写 .qpanel + 结果转换） | 406 ms | — | 记录；主要开销是临时 .qpanel 写盘（408 ms/300×965） |
| Python 参考引擎同场景 | 440 ms | — | — |
| C++ / Python 参考速度比 | 169× | ≥50× | 通过 |
| Panel.validate 全量哈希 | 正常 | — | 快路径不校验数据区；validate/CI 显式校验 |
| 5500×20y 全市场 / 10000 组 sweep / 峰值 RSS | 未跑（nightly） | <5min / <4GB | 未验证 |
| 1→N 线程逐位一致 | C++ 测试覆盖（单线程引擎 + 固定归约） | 一致 | 通过 |

说明：`make verify-cpp` 使用上述小集，全市场 5500×20y 与 10000 组参数是 nightly/后续性能任务，
结果必须实测后填入，不回填未测数字。Python 包装层可通过复用已打开 Panel/异步写盘优化。

## Regression gate

`make perf-gate` runs `scripts/verify_cpp.py` on the deterministic 300×965 panel and
compares open / 20-factor / backtest / C++-vs-reference ratio against
`docs/performance-baseline.json` with generous local tolerances (2–2.5× max, ratio floor
0.5×). The absolute thresholds in `verify_cpp.py` remain the CI gate; `perf-gate` is the
local early-warning check for silent multi-fold slowdowns.

## 规模基准（scripts/scale_bench.py）

上表「5500×20y 全市场 / 峰值 RSS」一行的可复现入口是 `make bench-scale`
（`scripts/scale_bench.py`）。数据为 SYNTHETIC，全部写入 `tempfile.TemporaryDirectory`，
不联网、不落永久产物；脚本测量合成面板构建、Parquet 写/读、`.qpanel` 写/打开（mmap）、
C++ engine 单次回测（3 次取最优）、进程峰值 RSS
（`resource.getrusage(RUSAGE_SELF).ru_maxrss`，macOS bytes / Linux KiB 统一归一化为 MiB）
与数据点规模。

```bash
make bench-scale                                            # 默认 800 证券 x 2020-2024
uv run python scripts/scale_bench.py --json                 # 机器可读输出
uv run python scripts/scale_bench.py --n-sec 5500 --json    # 全市场规模（需足够内存）
```

### 本机实测（2026-11-02，默认规模；非全市场）

机器：Apple M2 Pro（10 核）/ 16 GB / macOS 27.2 / Python 3.12.8 / Release。数据：
800 证券 × 2020-01-02..2024-12-31 = 1208 个合成交易日、17 个面板字段、965,259 根 bar、
966,400 个矩阵点。

| 项 | 实测 | 说明 |
|---|---:|---|
| 合成面板构建 | 1.28 s | 含 15,185 条 PIT 财务、10 条公司行动 |
| Parquet 写 | 1.36 s | 45.9 MiB（zstd，bars 按年分区） |
| Parquet 读（bars） | 0.08 s | 965,259 行 |
| `.qpanel` 写 | 1.70 s | 125.5 MiB（17 字段 × time_sec 布局） |
| `.qpanel` 打开（mmap） | 0.3 ms | 快速路径 |
| C++ engine 单次回测 | 8.8 ms | 月度调仓、前 50 等权、trace=summary |
| 峰值 RSS | 1594.9 MiB | 进程峰值；合成面板生成阶段占大头 |
| 总墙钟 | 5.46 s | 默认规模 |

> 本机实测，非全市场：800 证券小集，用于本地趋势与量级判断，不是 CI 门禁。
> 全市场 5500×20y 需在内存足够的机器上跑 `--n-sec 5500` 后回填数字，未实测前不写。
> 按默认规模线性估算，全市场生成阶段峰值约 6.9×（≈7.5 GiB），再加 `.qpanel` 字段矩阵
> （5500×1208×17×8 B ≈ 862 MiB）；建议 ≥16 GiB 空闲内存并预留时间，脚本在估算峰值
> 超过 4 GiB 时会打印警告。

短窗口（不足 120 个合成交易日）会自动向前补齐再裁剪到请求区间，因此
`--n-sec 200 --start 2023-01-03 --end 2023-06-30` 这类冒烟命令也能跑（约 1.7 s）。
数字为单次运行，重复运行约有 ±10% 波动；绝对门禁仍以 `make verify-cpp` / `make perf-gate` 为准。
