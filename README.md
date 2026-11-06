# QuantCore

简体中文 · [English](README.en.md)

**把 A 股策略想法，做成可以比较、复现和继续研究的实验。**

QuantCore 是以 **C++20 回测引擎**为核心的本地量化研究工作台。
从行情与数据检查，到策略回测、实验对比、稳健性分析和模拟账户，都可以在同一套界面里完成；数据与实验记录保存在自己的电脑上。

[![CI](https://github.com/feiiiiii5/QuantCore/actions/workflows/ci.yml/badge.svg)](https://github.com/feiiiiii5/QuantCore/actions/workflows/ci.yml)
[![C++20](https://img.shields.io/badge/core-C%2B%2B20-00599C)](cpp/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[本地运行](#本地运行) · [使用教程](docs/TUTORIAL.md) · [架构](docs/ARCHITECTURE.md) · [验收记录](docs/acceptance-report.md)

![实验对比：归一化净值、指标差值与研究条件](docs/screenshots/research-comparison.png)

*界面中的示例为 SYNTHETIC 合成数据。QuantCore 当前用于研究与模拟，不连接券商或提交真实委托。*

## 从一个想法开始

例如，你想研究“过去一段时间表现较强的股票，之后是否仍然较强”：

1. **准备数据**：先运行内置合成示例，或导入自己的数据，检查覆盖率、缺口与价格异常。
2. **定义策略**：选择动量、双均线等模板，调整参数；进阶使用可以编写表达式或本地策略插件。
3. **运行回测**：设置区间、初始资金、费用与成交规则，查看净值、回撤、指标及逐笔交易。
4. **比较实验**：沿用原实验保存的数据与参数生成新实验，对照归一化曲线、指标差值和假设差异。
5. **检查敏感性**：对保存的实验运行成本敏感性或 Monte Carlo，选择多份实验计算 PBO。因子诊断、参数扫描和固定参数分段回测另行配置；模拟账户支持逐日回放。

## 结果旁边，保留研究条件

**知道比较的是什么。** 实验对比按记录的初始资金归一化，并列出数据、区间、资金、费用与规则的差异；缺失的条件会标为未知。

**继续使用同一份数据。** “沿用数据与参数”读取原实验的快照或已保存面板，保留配置并记录新实验的来源。修改参数时，能区分策略变化与数据变化。

**留下可核对的记录。** 实验保存策略、参数、引擎版本、数据引用或面板，以及结果和报告；replay 可以重跑并核对净值、交易与指标。跨版本差异仍需检查。

## 主要能力

| 工作 | 可以完成什么 |
|---|---|
| 行情与选股 | 指数、自选、K 线、表达式选股；可选公开实时行情，界面标明数据状态 |
| 数据管理 | 数据导入、覆盖率与缺口检查、价格一致性检查、快照及数据指纹 |
| 策略与回测 | 模板、表达式、本地插件；C++ 日线回测、费用、T+1、手数、现金分红与送转处理 |
| 实验管理 | 参数与数据留存、来源追踪、归一化比较、条件差异、重跑核对、报告导出 |
| 研究分析 | 因子 IC/分层/衰减、参数扫描、固定参数分段回测、行业归因、PBO、成本敏感性与 Monte Carlo |
| 模拟账户 | 历史数据逐日回放、委托与持仓、T+1、部分成交、信号 CSV 导出、多策略组合 |

成本敏感性把费用倍数作为独立情景，逐项展示收益、Sharpe、回撤与以元计价的费用：

![成本敏感性：费用情景、收益变化与指标明细](docs/screenshots/cost-sensitivity.png)

## 本地运行

源码运行环境：**macOS 或 Linux**，Python 3.12、[uv](https://docs.astral.sh/uv/)、C++20 编译器、CMake ≥ 3.26、Ninja、Node.js ≥ 20 与 pnpm。
界面目前以中文为主，支持深浅色、新手/专业模式和移动端布局。

```bash
git clone https://github.com/feiiiiii5/QuantCore.git
cd QuantCore

# 安装 Python 依赖并编译 C++ 扩展
uv sync --frozen --python 3.12 --default-index https://pypi.org/simple

# 安装并构建界面
pnpm -C ui install --frozen-lockfile
pnpm -C ui build

# 生成合成数据、快照与第一份回测报告
uv run --no-sync qc demo --data-root data

# 打开本地工作台，读取同一数据目录
uv run --no-sync qc serve --data-root data --port 8000 --open
```

安装依赖需要联网。安装完成后的合成演示与本地研究可以离线运行，示例数据明确标为 `SYNTHETIC`。
服务只监听本机 `127.0.0.1`；打开后可在“实验”查看演示结果，再沿用数据与参数继续研究。

完整安装说明、真实数据导入与故障排查见 [快速上手](docs/QUICKSTART.md) 和 [本地测试](docs/LOCAL-TESTING.md)。

## C++ 核心与应用架构

| 层 | 技术与职责 |
|---|---|
| 原生核心 | **C++20 `qcore`**：`.qpanel` 面板读写、原生数值内核、日线事件驱动回测、账本与费用计算；通过 pybind11 供 Python 调用 |
| 应用层 | Python / FastAPI：数据接入、策略编排与表达式求值、实验、研究分析、模拟账户及 HTTP/WebSocket API |
| 界面 | TypeScript / React 19 / Vite：行情、策略、回测、实验与研究工作流 |
| 本地存储 | Parquet 数据、DuckDB 查询、SQLite 状态，以及引擎使用的 `.qpanel` 快照 |

生产回测必须经过原生引擎，C++ 扩展缺失时明确报错。Python 参考回测引擎仅用于测试；模拟账户撮合与部分研究计算仍在 Python 层。

### 可核对的验证记录

2026-11-06 的本地验收：Python **450 通过 / 2 跳过**、C++ **100/100**、前端 **29 通过**、真实服务浏览器 **19/19**，以及 C++/参考实现差分 **6/6**、既有 C++ 验证脚本、类型与构建检查。选股接口在相同 100 证券合成数据下耗时中位数由 **628ms 降至 36ms**，返回结果一致；方法与范围见 [性能记录](docs/PERFORMANCE.md)。
范围、原实现失败证据和未验证项见 [验收报告](docs/acceptance-report.md)；CI 的当前状态以上方链接为准。

## 数据与当前范围

网络数据接入默认关闭。可选历史与实时公开源有深度、授权、复权及公司行为近似等限制；实时行情仅作展示，不是授权 L2 行情源。
滚动验证目前为固定参数分段回测，稳健性指标是研究工具。Windows 目前提供 Python smoke 和未签名客户端壳，完整 C++ 后端尚不支持。

当前阶段以本地研究与测试为主，尚未进行生产部署验收。历史表现不代表未来，不构成投资建议。
详情见 [数据许可](docs/DATA-LICENSES.md)、[回测语义](docs/engine-semantics.md) 与 [规则来源](docs/rules-sources.md)。

## 文档与贡献

- **开始使用**：[教程](docs/TUTORIAL.md) · [快速上手](docs/QUICKSTART.md) · [本地自检](docs/LOCAL-TESTING.md)
- **了解系统**：[架构](docs/ARCHITECTURE.md) · [策略指南](docs/strategy-guide.md) · [API](docs/UI-API.md)
- **检查证据**：[验收报告](docs/acceptance-report.md) · [开发进度](docs/PROGRESS.md) · [性能记录](docs/PERFORMANCE.md)
- **参与开发**：[贡献指南](CONTRIBUTING.md) · [Issues](https://github.com/feiiiiii5/QuantCore/issues)

代码采用 [Apache-2.0](LICENSE) 许可证。第三方依赖与数据使用条件见 [数据许可](docs/DATA-LICENSES.md)。
