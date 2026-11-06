# QuantCore 快速上手

先用合成示例跑通 C++ 回测和界面，再导入自己的数据。完整操作说明见[使用教程](TUTORIAL.md)。

## 1. 准备环境

完整源码运行目前支持 macOS 或 Linux。需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、C++20 编译器、CMake ≥ 3.26、Ninja、Node.js ≥ 20 和 pnpm。
Windows 目前只有 Python smoke 与未签名客户端壳，完整 C++ 后端尚不支持。

```bash
git clone https://github.com/feiiiiii5/QuantCore.git
cd QuantCore
uv sync --frozen --python 3.12 --default-index https://pypi.org/simple
pnpm -C ui install --frozen-lockfile
pnpm -C ui build
```

`uv sync` 会安装项目并编译 `_qcore` 原生扩展。安装阶段需要联网；镜像与工具链排查见 [DEV-SETUP.md](DEV-SETUP.md)。

## 2. 生成第一份实验

```bash
uv run --no-sync qc demo --data-root data
```

这条命令会生成明确标记为 `SYNTHETIC` 的数据、建立快照、通过 C++ 引擎运行示例策略，并保存实验与 HTML 报告。
输出 JSON 包含 `engine_backend: "cpp"`、`snapshot_id`、`run_id` 和报告路径。

示例用于熟悉流程，不能解释为真实市场结论。

## 3. 打开本地工作台

```bash
uv run --no-sync qc serve --data-root data --port 8000 --open
```

演示与服务使用相同的 `data` 目录，因而能读取刚生成的快照。实验记录默认位于 `experiments`。
服务只监听 `127.0.0.1`；终端输出的带 token 地址会由 `--open` 打开，token 保存后会从地址栏移除。

打开后可以：

1. 在“实验”查看刚生成的回测结果。
2. 点击“沿用数据与参数”，修改一个参数生成有来源链接的新实验。
3. 选中两份实验，对比归一化曲线与数据、资金、费用和规则差异。
4. 点击“继续研究”，对保存的实验运行成本敏感性或 Monte Carlo；PBO 需要选择至少两份实验。

因子诊断、参数扫描和固定参数分段回测有独立配置，不会自动继承当前实验的全部设置。
界面支持新手/专业模式、深浅色、移动端布局，以及 ⌘K / Ctrl+K 命令面板。

## 4. 使用自己的数据

网络数据接入默认关闭。导入后，先检查数据质量，再构建快照，并在回测时明确选择该快照。
**CLI 回测省略 `--snapshot` 时会新建合成数据，不会自动使用最近导入的数据。**

查看已有快照：

```bash
uv run --no-sync qc snapshot list --snapshots-root data/snapshots
```

使用 CLI 时，将实际快照 ID 传给 `qc backtest run` 的 `--snapshot` 参数，并保持 `--snapshots-root data/snapshots`；也可以直接在回测界面选择该快照。

### 可选 Sina 公开日线

```bash
QC_ALLOW_NETWORK=1 uv run --no-sync qc data update --provider sina \
  --codes 600000,000001,300750 --start 2024-01-01 --end 2026-10-31 --data-root data
uv run --no-sync qc snapshot build --data-root data --snapshots-root data/snapshots
uv run --no-sync qc data integrity --snapshots-root data/snapshots
```

随后按上面的方式明确选择构建出的快照。公开源并非授权行情 feed；日线深度、成交额估算、复权和公司行为近似等限制见 [DATA-LICENSES.md](DATA-LICENSES.md)。本次文档更新未重新验证真实网络导入。

Tushare 等 provider 接口属于可选集成，真实 Token 路径及其网络许可配置仍需验证，不作为这份快速上手的运行前提。

### 可选实时行情

```bash
QC_ALLOW_NETWORK=1 uv run --no-sync qc serve --data-root data --port 8000 --open
```

公开实时源仅作展示，不是授权 L2 行情，不连接券商。关闭网络时显示离线数据状态。

## 5. 本地自检与开发

```bash
uv run --no-sync qc doctor
```

开发验证需要额外安装开发依赖：

```bash
uv sync --frozen --all-extras --python 3.12 --default-index https://pypi.org/simple
```

相关命令与范围见 [LOCAL-TESTING.md](LOCAL-TESTING.md)，数据和接口契约见 [UI-API.md](UI-API.md)。
当前阶段以本地测试为主，不部署上线，也不提供真实下单能力。
