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
