# PERFORMANCE — 基准方法与门禁

## 环境（开发机）
- Apple M2 Pro（10 核，16GB），macOS 27.2，Apple clang 21，Release `-O3 -DNDEBUG`；无 `-march=native`。
- CI 小集：GitHub Actions macOS/Ubuntu；nightly 全量。

## 基准集
- 计划中的合成全市场目标：约 5500 证券 × 20 年日线（含掩码），固定 seed；本轮未执行该规模，CI 用小集。
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

## 2026-11-06 R7 本地复测

同一开发机，基线 `406b687`，原生引擎 0.1.1，Release，无 `-march=native`。最终停牌估值修正后，`scripts/verify_cpp.py` 使用原有 SYNTHETIC 300×965 小集：打开面板 0.213ms、20 因子 25.73ms、原生回测 3.08ms、含 Python 包装回测 470.54ms、Python 参考 491.43ms，原生/参考约 159.50 倍；差分 6/6，既有门禁通过。此处为脚本当次读数，不是五次中位数，也未扩展为全市场结论。

选股 API 使用 SYNTHETIC 100 证券、2023-01-03..2023-12-29、seed=11、表达式 `close`、limit=5，matched_count=99。相同进程环境与面板，分别运行基线和当前路由各五次，逐项比较响应完全一致：

| 版本 | 五次耗时（ms） | 中位数（ms） |
|---|---|---:|
| `406b687` 路由 | 695.29 / 724.40 / 627.68 / 541.86 / 545.91 | 627.68 |
| 当前路由 | 36.37 / 34.71 / 35.48 / 41.29 / 39.20 | 36.37 |

约 17.26 倍提升来自复用字段矩阵、排序/截断后再构造结果，避免每个命中项重新 pivot 全历史；不包含数据导入或网络开销。`tests/test_screener_performance.py` 同时校验实际 API 行为与字段物化次数，未设易受机器波动影响的固定耗时断言。5500×20 年、10000 组参数和全市场峰值内存仍未验证。

## 2026-11-06 Q-005：面板与策略热点

基线 `0f0e2af`，Apple M2 Pro / macOS 27.3 / Python 3.12.8，原生版本 0.1.1。输入是固定 seed=123 的 SYNTHETIC 200 证券 × 965 日、192088 根 bar；各取五次中位数。完整样本、参数与指纹保存在 [performance-q005.json](performance-q005.json)。

| 路径 | 旧实现/参考 | 优化后 | 比例 |
|---|---:|---:|---:|
| 17 字段 `.qpanel` 导出 | 290.19 ms | 82.80 ms | 3.50× |
| trend_momentum 信号生成 | 129.61 ms | 22.00 ms | 5.89× |
| liquid_reversal 信号生成 | 161.36 ms | 42.09 ms | 3.83× |
| defensive_low_vol 信号生成 | 129.15 ms | 24.91 ms | 5.18× |

导出使用旧提交函数与新函数在同一面板上配对测量，输出文件 SHA-256 完全相同。信号参考在同一进程恢复旧 `pivot_table(..., aggfunc="last")` 算法；优化复用单个只读视图的坐标并散射字段，三候选的全部权重逐值相同、SHA 不变。重复/缺失/乱序/轴外数据及全部十款模板亦有差分回归；可变 PanelData 每次重新建立坐标，不使用跨变更缓存。

当前原生回测入口 **1.73 ms**；预热 PanelData 包装 **36.75 ms**，预热且已验证的 Snapshot 包装 **9.65 ms**。这三项使用已生成的月度等权权重；信号耗时单列，不把原生入口称为端到端。PanelData 包装仍包含约 **30.35 ms** 的内容哈希检查，Snapshot 的已有快路径不跳过变更校验。净值与成交一致（448 笔），完整基准可运行 `QC_ALLOW_NETWORK=0 uv run --frozen python scripts/bench_backtest.py`。

另一次既有 `verify_cpp.py` 小集（300×965）测得原生 3.53ms、含冷导出包装 189.91ms、参考 519.65ms，差分 6/6 与验证门禁通过。这是脚本单次读数；不与上面的五次中位数混用，也不构成全市场、p99 延迟或实盘吞吐结论。未改变 C++ 构建选项，未使用 `-march=native`。

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
