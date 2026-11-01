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
