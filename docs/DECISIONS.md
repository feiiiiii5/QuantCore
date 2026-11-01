# DECISIONS — 架构与选型 ADR

> 格式：编号 / 决策 / 状态 / 理由 / 基准或替代。用户任务书的硬约束优先于本文。

## ADR-001 核心自研、外围采用成熟 GitHub 方案
- 状态：accepted
- 理由：qcore 的定点账本、.qpanel、回测语义是本项目差异化与可验证性的核心，必须自研；
  pybind11、scikit-build-core、Catch2、Google Benchmark、numpy/pandas/pyarrow/duckdb、
  pydantic/FastAPI、React/Vite/ECharts/lightweight-charts 等直接采用成熟方案。GPL/AGPL 依赖不进入分发包。

## ADR-002 C++20 + CMake + Ninja + scikit-build-core + pybind11
- 状态：accepted
- 理由：用户指定；macOS arm64/x64 与 Windows 优先；pybind11 提供 NumPy 零拷贝与 GIL 控制。

## ADR-003 定点数
- 状态：accepted
- 价格/金额 = int64，1e-4 元；数量 int64 股；费用取整规则集中实现并有黄金用例。
- 理由：跨平台逐位一致、避免浮点误差；因子/指标独立用 double。

## ADR-004 .qpanel 格式
- 状态：accepted
- 64B 对齐、列式 SoA、字段目录、内容哈希、mmap 只读、多进程共享；支持 [证券][时间] 与 [时间][证券] 两种布局。
- 更新 = 新快照（Windows 映射不可覆盖）。

## ADR-005 前端图表
- 状态：proposed（M6 前定稿）
- K 线：KLineChart 与 lightweight-charts 均候选；按许可证、画线能力与包体积比较后定稿。
- 分析图：ECharts；表格：TanStack Table + 虚拟滚动；编辑器：Monaco。

## ADR-006 不引入 OpenMP
- 状态：accepted
- 理由：macOS 打包与运行时复杂；自研固定线程池，任务粒度=一次回测/一次因子计算。

## ADR-007 数据源
- 状态：accepted
- Tushare Pro 优先；RQData 可选（用户许可）；AKShare/mootdx 补充（契约测试）；LocalFile/Synthetic 首发。
- 网络层不做运行时依赖；快照与 .qpanel 是引擎输入。

## ADR-008 仅研究与模拟
- 状态：accepted
- 不实现真实下单；BrokerGateway 默认禁用；所有界面/报告带免责声明。

## ADR-009 .qpanel 打开校验分级
- 状态：accepted（M1）
- 默认 `Panel::open(path)` 只做 O(1) 级结构校验（魔数/版本/大小/section 边界/64B 对齐/dates/security/字段表），
  满足“打开快照 <200ms”；`Panel::open(path, true)` 或 `Panel::validate(path)` 做全量内容哈希校验（O(file size)）。
- 理由：4GB 面板全量哈希约 5s，不能作为热路径默认；写入端仍计算并存储内容哈希，快照完整性可用 validate/CI 校验。

## ADR-010 表达式 DSL 语义
- 状态：accepted（M4）
- NaN 统一传播；ts_* 严格窗口；rank/ts_rank 为 average-rank 百分位；delay(x,n)=x[t-n]；字段只读 ≤t。
- 窗口必须字面量整数；截面函数在 t 时刻对全部证券计算；非法输入抛 std::invalid_argument（Python ValueError）。
- 性能：当前逐点/按列求值，未达“20 因子 <3s”门禁；优化路径为 DAG 节点物化 + 增量滚动，排入 M7。
