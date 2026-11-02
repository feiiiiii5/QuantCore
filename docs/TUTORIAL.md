# TUTORIAL — 零基础跑通 QuantCore

这份教程只做一件事：带你在本机看到第一份回测结果，并知道它能不能信。
QuantCore 只做研究和模拟，不连接券商、不发真实委托。合成数据都会标 `SYNTHETIC`。

## 1. 安装（macOS / Windows）

先准备：Python 3.12（用 uv 管理）、CMake ≥3.26、Ninja、C++20 编译器、Node ≥20、pnpm。

macOS：

```bash
xcode-select --install
brew install uv cmake ninja node pnpm
git clone https://github.com/feiiiiii5/QuantCore.git
cd QuantCore
make setup
pnpm -C ui install
pnpm -C ui build
```

Windows（实验性；C++ 核心尚未在真实 Windows 机器上验证）：

- 先装 Visual Studio 2022 Build Tools（勾选“使用 C++ 的桌面开发”）、CMake、Ninja、Node、pnpm、uv。
- 更稳的做法：在 WSL2 的 Ubuntu 里按 macOS/Linux 步骤执行。
- 原生 Windows 若卡在编译，以 WSL2 为准。

```powershell
git clone https://github.com/feiiiiii5/QuantCore.git
cd QuantCore
uv python install 3.12
uv sync --all-extras --python 3.12
pnpm -C ui install
pnpm -C ui build
```

大陆网络镜像：

```bash
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
pnpm config set registry https://registry.npmmirror.com
# PowerShell 用 $env:UV_DEFAULT_INDEX="..." 这种写法
```

检查环境：

```bash
uv run qc doctor
```

**你应该看到：** `qc doctor` 的 `status` 为 `ok`、`engine_backend` 为 `cpp`、`fail` 为 0，且 `ui/dist/index.html` 存在。

## 2. 启动

```bash
uv run qc serve --port 8000 --open
```

- 只监听 `127.0.0.1`；终端会打印带 token 的 URL，浏览器打开后 token 自动保存。
- 端口被占用就换一个：`uv run qc serve --port 8001 --open`。
- 关闭服务：回到终端按 `Ctrl+C`。

**你应该看到：** 浏览器打开首页「今日」，底部状态栏显示数据源、快照日期、引擎和免责声明。

## 3. 首页「今日」怎么看

从上到下：

1. 市场状态带：上证 / 深成 / 创业板 / 科创50；休市时显示最近收盘和“休市”。
2. 我的自选：没设置时是“添加自选”引导。
3. 新手进度：4 步清单。
4. 最近研究：研究卡片 + 体检徽章。
5. 数据体检摘要：黄色/红色表示数据不够可信。
6. 主按钮「开始一次研究」。

**你应该看到：** 没有数据时是空态和「一键示例」；点它会生成 SYNTHETIC 数据并跳到结果。

## 4. 新手清单 4 步

1. **生成示例数据**：生成合成面板和第一个快照，不联网。
2. **跑第一个回测**：用白话策略预设跑一次。
3. **看懂结果**：到实验页看收益、回撤、夏普和可信度。
4. **查看数据体检**：到数据页确认覆盖率、缺口和 OHLC 自洽。

完成一步会记录到本机；数据、回测、结果也会自动检测。刷新页面不会丢。

**你应该看到：** 进度从 `0/4` 到 `4/4`，完成的步骤打勾。

## 5. 行情页：实时还是离线

- 绿点「实时」：显示最后更新时间。
- 灰点「休市」：显示最近收盘。
- 黄点「离线」：显示快照日期。

网络默认关闭；关闭时全站不发网络请求。开启方式：启动前设置 `QC_ALLOW_NETWORK=1` 再重启 `qc serve`；**设置 → 数据与网络** 可查看当前状态。

**你应该看到：** 状态带或行情页右上角有状态点；离线时明确写“离线快照”，不会假装实时。

## 6. 跑第一个回测

**研究 → 回测**，三步：

1. **策略**：选一个预设，比如“低波动防守”，也可以换模板。
2. **数据与区间**：选快照和起止日期。
3. **运行**：等进度到 100%。

结果页先看这几个数：

- **总收益**：整段区间的累计涨跌，已经扣掉交易成本。
- **年化**：按年折算；区间短会失真。
- **最大回撤**：从最高点最多跌多少；越接近 0 越稳。
- **夏普**：每承担一份波动换来多少收益；要结合回撤和交易次数一起看。
- **可信度徽章**：数据体检、成本后口径、是否样本外；看到“样本内 / 未做样本外验证”或黄色/红色提示，就别把回测当结论。研究页可继续做样本外、过拟合和成本敏感性检查。

**你应该看到：** 四张指标卡 + 净值/回撤图 + 交易表 + “SYNTHETIC / 数据体检”提示；实验自动保存到 `experiments/`。

## 7. 数据体检与真实数据导入

数据页先看体检：状态徽章、覆盖率、缺口 Top N、OHLC 自洽、涨跌停、复权连续性、修复提示。

导入真实数据：

- **东方财富**：免 token，但仍然需要网络；后端未就绪时按钮会灰显。
- **Tushare**：需要 token；未配置时按钮会灰显。

```bash
export TUSHARE_TOKEN=你的_token
# PowerShell: $env:TUSHARE_TOKEN="你的_token"
```

网络默认关。启动前设置 `QC_ALLOW_NETWORK=1` 再重启 `qc serve`；命令行同理：`QC_ALLOW_NETWORK=1 uv run qc ...`。
导入后先建快照，再看体检；体检通过再回测。

**你应该看到：** 数据页状态从黄/红变绿；快照列表多一条；结果页的体检徽章同步更新。

## 8. 模拟交易

**模拟**页：新建会话（选快照、初始资金）→ 推进交易日 → 提交委托。

- **T+1**：当天买入的股票当天不能卖；下一交易日才可用。
- **费用**：佣金（最低 5 元）、印花税（仅卖出）、过户费（沪市）、规费；逐笔成交分别计费。
- **部分成交**：每单每日最多成交当日成交量的 10%（默认参与率），剩余部分保持“部分成交”，下一交易日继续。
- 市价单按下一交易日开盘价撮合；限价单触价才成交。

**你应该看到：** 委托状态从“待成交”到“部分成交/已成交”；持仓“可用”次日增加；成交表有费用。

## 9. 常见问题

- **端口被占用**：换端口 `uv run qc serve --port 8001 --open`，或结束占用 8000 的进程。
- **401 / 页面空白**：确认 `qc serve` 还在跑；访问终端打印的带 token URL，或在设置页填 token；可用 `QC_SERVER_TOKEN=...` 固定 token。
- **没有数据 / 回测没结果**：先点「一键示例」，或运行 `uv run qc data update --provider synthetic` 再 `uv run qc snapshot build`。
- **网络开关**：默认关；启动前 `export QC_ALLOW_NETWORK=1`（PowerShell 用 `$env:QC_ALLOW_NETWORK="1"`）再重启 `qc serve`；**设置 → 数据与网络** 可看状态。关闭时不要期待实时报价。
- **为什么没有实盘**：产品只做研究与模拟，`BrokerGateway` 默认禁用，不接券商、不发真实委托。
- **引擎 missing**：先 `make build`，再 `uv run qc doctor`；仍失败看 doctor 的提示。

**你应该看到：** 每个问题都有明确下一步，不会出现“看起来能下单”的入口。

## 10. 免责声明

QuantCore 仅用于研究与模拟，不构成投资建议。合成数据标 `SYNTHETIC`，不是真实行情；历史表现不代表未来。回测和模拟结果都可能因数据、规则与成本假设而变化。

**你应该看到：** 页面底部状态栏、报告和本教程都保留这句话。
