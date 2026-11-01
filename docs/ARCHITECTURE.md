# ARCHITECTURE — QuantCore 总览

```
React UI (M6) ⇄ HTTP/WS (127.0.0.1, Bearer) ⇄ FastAPI qc-server ⇄ job worker ⇄ qcore (C++20)
                                                        │
                                              SQLite state / Parquet+DuckDB data / .qpanel
```

## 层
1. **数据层**：Provider → ingest → quality → immutable snapshot → Parquet(权威) + DuckDB(查询) + `.qpanel`(引擎输入)。
2. **qcore**：定点类型、日历、面板 mmap、内核/指标、表达式、回测引擎、绩效、并行 sweep、pybind11。
3. **Python 控制面**：`qc` CLI/SDK、策略加载/沙箱、实验存储、报告、服务与任务队列。
4. **UI**：React 19 + Vite + ECharts/KLine 库 + Monaco + 虚拟表格；本地打包，零 CDN。
5. **桌面**：Electron（M10）。

## 关键契约
- `quantcore._qcore` 暴露 `Panel`、`BacktestConfig`、`Engine.run(weights)`、`kernels`、`sweep`。
- Python 侧 `engine_backend = "cpp"`；纯 Python 参考实现只在 `tests/reference/`。
- 快照不可变；内容哈希；数据访问器只返回 ≤now。

## 目录
见 `AGENTS.md`。
