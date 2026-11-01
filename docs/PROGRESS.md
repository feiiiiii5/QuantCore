# PROGRESS — 当前进度

> 每阶段结束记录：完成项、验证命令与结果、已知缺口、下一步、续跑方法。上下文清空后据此恢复。

## 当前状态（2026-11-01 晚）
- M0 完成：`make setup/test`、wheel 构建、`engine_backend=cpp`。
- M1 完成（C++）：types/calendar/tpool/.qpanel(两种布局)/17 个内核+10 指标/零拷贝绑定；C++ ctest 95/95、36 个 M1 用例 5828 assertions、ASan/UBSan/TSan、36 项 benchmark。
- M2 基本完成：Synthetic/LocalFile/Tushare(fixture)/AKShare/mootdx provider；摄取/质量/快照(内容寻址+PIT 元数据)/Parquet+DuckDB+SQLite；合成快照可建并写 .qpanel；CLI data/snapshot 已跑通。
- M3 完成：event-driven 引擎、规则/费用/T+1/手数/涨跌停/停牌/除权除息/trace/指标；C++ 95/95；C++ vs Python reference 差分 6 个用例通过；引擎 300×965 月度调仓 2.6ms。
- M4 部分：表达式 DSL（tokenizer/parser/CSE/eval，17 用例 309 assertions）、7 模板、lookahead/sandbox 接口、实验存储/HTML 报告/CLI backtest/replay 骨架；CLI 合成端到端已跑通。
- M5 部分：FastAPI 本地服务/任务队列/安全骨架/API 测试（py-platform 收尾中）。
- M6 基础壳：UI 六页 + 主题/密度 + API client + 空态；`pnpm build/test` 通过；未接真实后端数据。
- M7–M10 未开始（仅文档/接口预留）。
- 本轮只读旧仓库；QuantCore 为全新仓库，未改申请季工作区。

## 验证命令与结果（本轮）
```bash
# C++
cmake -S . -B build/cmake-lead -G Ninja -DCMAKE_BUILD_TYPE=Release -DQC_BUILD_PYTHON=OFF -DQC_BUILD_TESTS=ON -DQC_BUILD_BENCH=ON
cmake --build build/cmake-lead -j8
ctest --test-dir build/cmake-lead --output-on-failure    # 100% tests passed, 95/95
# Python 扩展
uv sync --reinstall-package quantcore --python 3.12
uv run python -c "import quantcore; print(quantcore.engine_backend())"   # cpp
# verify-cpp（实测）
uv run python scripts/verify_cpp.py
#   open 0.20ms / 20 factors 21.5ms / engine 2.6ms / ratio 169x / differential pass
# CLI 合成端到端
uv run qc data update --data-root /tmp/qc_cli/data --n-sec 40 --start 2022-01-04 --end 2023-12-29
uv run qc snapshot build --data-root /tmp/qc_cli/data --snapshots-root /tmp/qc_cli/snapshots
uv run qc backtest run --snapshots-root /tmp/qc_cli/snapshots --experiments-root /tmp/qc_cli/experiments --template dual_ma
# UI
pnpm -C ui build && pnpm -C ui test
```

## 已知缺口（按优先级）
1. Python pytest 仍在收尾（reference 测试的平盘 fixture、board 手数断言、API/CLI/provider 测试）；`make lint` ruff/mypy 需清零。
2. 实验产物目前是 summary/metadata/report/strategy；equity/positions/orders/trades/trace 的 Parquet 产物与完整 replay 待补。
3. C++ 并行 sweep、10k 参数、5500×20y 全市场基准、峰值 RSS 未实测。
4. Tushare 真实网络路径无 Token 未验证；AKShare/mootdx 仅契约/冒烟；数据源条款见 DATA-LICENSES。
5. 规则 TODO(verify)：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。
6. M6 UI 未接后端数据；M7–M10 未实现；Electron 未做。
7. `.qpanel` 全量校验非默认（ADR-009）；Windows mmap/CI 未实测。

## 下一步
1. py-platform 收尾测试/lint/CLI/API；Lead 跑 `make test`、`make lint`、`make verify-cpp`。
2. 补实验 Parquet 产物与 replay 一致性；再补 M7 因子分析/sweep。
3. ✅ 已上传 GitHub public 仓库：https://github.com/feiiiiii5/QuantCore （main 分支，Apache-2.0）。
4. GitHub Actions `ci`：macOS + Ubuntu 全绿（push 触发，run 41321931285）；Windows 未验证，未纳入 push CI。
5. 下一步（未做）：M5 WebSocket/取消/通知、M6 后端接线、C++ 并行 sweep、M7 因子分析、真实 Tushare 验证、Windows 端口。

## 续跑方法
```bash
cd /Users/fei/Desktop/QuantCore
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
make setup && make ci-local
```
