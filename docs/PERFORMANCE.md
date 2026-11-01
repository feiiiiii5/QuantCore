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
