# QUICKSTART — 中文快速上手

## 1. 安装
- macOS（Apple Silicon/Intel）或 Windows（Linux 其次）。
- 依赖：Python 3.12、CMake ≥3.26、Ninja、Node ≥20 + pnpm（UI 可选）、C++20 编译器（Apple clang ≥15 / MSVC 2022 / gcc ≥12）。
- 中国大陆网络镜像见 `DEV-SETUP.md`。

```bash
git clone <repo> QuantCore && cd QuantCore
make setup
```

## 2. 合成数据（三步跑通）
```bash
uv run qc data update --provider synthetic --securities 200 --years 5
uv run qc snapshot build --dataset synthetic
uv run qc backtest run --strategy ma_cross --start 2021-01-01 --end 2025-12-31
```
输出会写明 `engine_backend == "cpp"`；结果含净值、回撤、指标与逐笔交易。

## 3. 真实数据（需要 Tushare Token）
```bash
export TUSHARE_TOKEN=...   # 或 uv run qc data config 写入系统钥匙串
uv run qc data update --provider tushare --start 20100101
uv run qc snapshot build --dataset tushare
uv run qc backtest run --strategy multi_factor --start 2020-01-01 --end 2025-12-31
```

## 4. 常见问题
- `engine_backend == "missing"`：先 `make build`。
- 数据导入失败：检查 `qc data quality` 报告；网络层只使用录制 fixture 做测试。
- 规则/费率未核实：见 `rules-sources.md`，代码与界面标 `TODO(verify)`。
