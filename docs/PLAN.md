# PLAN — QuantCore 里程碑

> 来源：用户 2026-11-01 的完整任务书。门禁通过才进入下一阶段；每阶段结束更新 `PROGRESS.md`。

| 阶段 | 内容 | 门禁 |
|---|---|---|
| M0 | 仓库、工具链、Makefile、CI、镜像、pybind11+NumPy 零拷贝 | `make setup test` 绿；wheel 可构建 |
| M1 | 定点类型、日历、.qpanel 读写、线程池、内核/指标、基准框架 | 与 numpy/pandas 对照通过；基准入库 |
| M2 | Provider 接口、Synthetic/Tushare(fixture)/LocalFile、摄取/质量/快照/PIT、Parquet+DuckDB+SQLite | 合成全市场快照可建；增量幂等；质量报告可出 |
| M3 | 回测引擎（先引擎语义文档）规则/费用/账本/执行/trace/指标；参考引擎/黄金/差分/属性/模糊/确定性 | 全绿且 §10 达标 |
| M4 | DSL、三档策略接口、沙箱、未来函数检测、模板、实验存储、报告、replay | `qc backtest` 端到端；engine_backend==cpp；replay 一致 |
| M5 | API/WS、任务队列、安全 | OpenAPI 契约测试；取消与崩溃恢复 |
| M6 | UI V1 六大模块、交易解释器、实验对比、数据中心、向导 | Playwright e2e；UI 预算 |
| M7 | 因子分析、并行参数搜索、稳定性、样本外/滚动、过拟合、归因、容量 | 门禁见任务书 |
| M8 | 创业板/科创板/北交所、分钟线、个股资料、ETF/可转债 | 门禁见任务书 |
| M9 | 历史回放、持续模拟、提醒、多组合、插件、信号导出、BrokerGateway(禁用) | 门禁见任务书 |
| M10 | Electron 封装、安装包、中文文档、SBOM、发布清单 | 门禁见任务书 |

## V1 范围
沪深主板日线现货多头；schema 与规则引擎按全板块设计。其余板块 M8。

## 性能初始门禁（§10）
- 打开快照 mmap < 200ms；20 因子全面板 < 3s（8 线程）；单次回测 < 1s；10000 组参数 < 5min（8 核）。
- 1→N 线程结果逐位一致；峰值内存 < 4GB；C++ vs Python 参考 ≥50×；回归 >10% 失败。
- 实测后可凭基准写明依据调整，不得造假。
