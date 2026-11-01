# QUICKSTART — 中文快速上手

## 1. 安装
- macOS（Apple Silicon/Intel）或 Windows（Linux 其次）。
- 依赖：Python 3.12、CMake ≥3.26、Ninja、Node ≥20 + pnpm、C++20 编译器（Apple clang ≥15 / MSVC 2022 / gcc ≥12）。
- 中国大陆网络镜像见 `DEV-SETUP.md`。

```bash
git clone https://github.com/feiiiiii5/QuantCore.git
cd QuantCore
make setup
```

## 2. 合成数据（三步跑通 CLI）
```bash
uv run qc data update --provider synthetic --n-sec 200 --start 2020-01-02 --end 2024-12-31
uv run qc snapshot build
uv run qc backtest run --template dual_ma --start 2021-01-01 --end 2024-12-31
```
输出会写明 `engine_backend == "cpp"`；结果含净值、回撤、指标与逐笔交易。

## 3. 启动本地工作台
```bash
pnpm -C ui build
uv run qc serve --port 8000 --open
```
- `qc serve` 只监听 `127.0.0.1`，需要 Bearer token；终端会打印带 token 的 URL，浏览器打开后 token 自动保存并从地址栏移除。
- 首次进入可用侧栏“**一键示例**”：生成 SYNTHETIC 面板/快照并跑一次示例回测，随后跳到实验页。
- 页面：行情 / 选股 / 策略 / 回测 / 实验 / 研究 / 数据 / 设置。
- 无快照时行情接口会用 40 只合成回退，便于先看 UI；正式研究请先建快照。

## 4. 前端开发
```bash
# 终端 A
uv run qc serve --port 8000
# 终端 B
pnpm -C ui dev
# Vite: http://127.0.0.1:5173，代理 /api /ws /health 到 8000
```
开发模式仍需在设置页填 token（或访问 `http://127.0.0.1:5173/?token=<token>`）。

## 5. 真实数据（需要 Tushare Token）
```bash
export TUSHARE_TOKEN=...   # 或按 DEV-SETUP 写入系统钥匙串
uv run qc data update --provider tushare --start 2010-01-01 --end 2024-12-31
uv run qc snapshot build
uv run qc backtest run --template multi_factor --start 2020-01-01 --end 2024-12-31
```
> 真实网络路径未在本次验收中跑通（无 Token）；请先用小样本验证质量报告。

## 6. 研究
- UI `/research`：因子 IC/分层/衰减、参数扫描热力图、滚动验证、行业归因。
- HTTP：`POST /api/research/factor`、`/sweep`、`/walk_forward`、`/attribution`，契约见 `UI-API.md`。
- 参数扫描服务端同步上限 200 组合；更大规模请用 CLI/离线任务（M7 C++ 并行 sweep 仍待补）。

## 7. 测试
```bash
make lint          # ruff + mypy
make test          # pytest + ctest
make verify-cpp    # C++ 后端/差分/性能
make e2e           # UI 构建 + 隔离 qc serve + Playwright（需要 Chrome）
```

## 8. 常见问题
- `engine_backend == "missing"`：先 `make build`，再 `uv run python -c "import quantcore; print(quantcore.engine_backend())"`。
- 页面空白/401：确认 `qc serve` 仍在运行；设置页填地址与 token；或访问 `/?token=<token>`。
- 数据导入失败：查看 `qc data quality` 报告；网络层测试使用录制 fixture。
- 快照/实验路径：默认 `data/snapshots/`、`experiments/`；`qc serve --data-root ...` 可隔离。
- 规则/费率未核实：见 `rules-sources.md`，代码与界面标 `TODO(verify)`；本项目不构成投资建议。
