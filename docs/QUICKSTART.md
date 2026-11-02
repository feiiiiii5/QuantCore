# QUICKSTART — 中文快速上手

> 完全零基础？先读 [TUTORIAL.md](TUTORIAL.md)：从安装到看懂第一个回测，每节都有“你应该看到”。

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

### 本地自检 / 一键演示
```bash
make doctor   # 环境自检（Python / C++ 扩展 / 前端构建 / 数据目录）
make demo     # 合成数据 + 快照 + 示例回测，一条命令跑通
```
完整的本地测试路线（verify-local / bench-scale / 故障排查）见 [`LOCAL-TESTING.md`](LOCAL-TESTING.md)。

## 3. 启动本地工作台
```bash
pnpm -C ui build
uv run qc serve --port 8000 --open
```
- `qc serve` 只监听 `127.0.0.1`，需要 Bearer token；终端会打印带 token 的 URL，浏览器打开后 token 自动保存并从地址栏移除。
- 首次进入首页「今日」可用“**一键示例**”：生成 SYNTHETIC 面板/快照并跑一次示例回测；新手模式默认开启，按首页清单 4 步即可上手。
- 页面：今日 / 行情 / 选股 / 策略 / 回测 / 实验 / 研究 / 数据 / 模拟 / 设置；⌘K（Ctrl+K）打开命令面板。
- 无快照时行情接口会用 40 只合成回退，便于先看 UI；正式研究请先建快照。
- 设计/交互规范见 [`DESIGN-SPEC.md`](DESIGN-SPEC.md)，产品理念见 [`PRODUCT.md`](PRODUCT.md)。

## 4. 前端开发
```bash
# 终端 A
uv run qc serve --port 8000
# 终端 B
pnpm -C ui dev
# Vite: http://127.0.0.1:5173，代理 /api /ws /health 到 8000
```
开发模式仍需在设置页填 token（或访问 `http://127.0.0.1:5173/?token=<token>`）。

## 5. 真实数据

### Sina 公开源（免 Token，联网）
```bash
# 网络默认关闭；显式开启后才允许外部请求。公开数据仅限自用、不得再分发。
QC_ALLOW_NETWORK=1 uv run qc data update --provider sina \
  --codes 600000,000001,300750 --start 2024-01-01 --end 2026-10-31 --data-root data
uv run qc snapshot build --data-root data --snapshots-root data/snapshots
uv run qc data integrity --snapshots-root data/snapshots   # 体检通过再回测
uv run qc backtest run --template dual_ma --start 2024-06-01 --end 2026-10-31
```
真实 3 只样本已实测：质量 passed、覆盖率 100%、integrity=ok、C++ 回测成功。成交额为估算、复权/公司行为为近似，详见 `DATA-LICENSES.md`。

### Tushare（需要 Token）
```bash
export TUSHARE_TOKEN=...   # 或按 DEV-SETUP 写入系统钥匙串
uv run qc data update --provider tushare --start 2010-01-01 --end 2024-12-31
uv run qc snapshot build
uv run qc backtest run --template multi_factor --start 2020-01-01 --end 2024-12-31
```
> 真实 Tushare 网络路径本轮未验证（无 Token）；请先用小样本验证质量报告。

### 实时行情（可选，联网）
`QC_ALLOW_NETWORK=1 uv run qc serve --open` 后行情页约每 3 秒刷新（Sina/Eastmoney 公开源，仅展示）；
关闭网络时显示最近快照并标注“离线快照”。接口见 `UI-API.md`。

## 6. 研究
- UI `/research`：因子 IC/分层/衰减、参数扫描热力图、滚动验证、行业归因、稳健性。
- HTTP：`POST /api/research/factor`、`/sweep`、`/walk_forward`、`/attribution`，契约见 `UI-API.md`。
- 参数扫描服务端同步上限 200 组合；更大规模请用 CLI/离线任务。

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
- 找不到页面：旧链接 `/` 会跳转到 `/today`；实时/真实数据相关按钮需先设置 `QC_ALLOW_NETWORK=1` 并重启 `qc serve`。
- 数据导入失败：查看 `qc data quality` 报告或数据页「数据体检」；少量坏行会被隔离并告警，网络层测试使用录制 fixture。
- 快照/实验路径：默认 `data/snapshots/`、`experiments/`；`qc serve --data-root ...` 可隔离。
- 规则/费率未核实：见 `rules-sources.md`，代码与界面标 `TODO(verify)`；本项目不构成投资建议。
