# DATA-LICENSES — 数据与依赖许可

## 数据源
| 来源 | 用途 | 许可/条款 | 再分发 |
|---|---|---|---|
| Tushare Pro | 优先数据源 | 以官方用户协议为准；Token 由用户自备 | 不随仓库分发数据 |
| RQData | 可选 | 商业许可，用户自备 | 不分发 |
| AKShare | 补充 | 以上游项目声明为准 | 不分发原始数据 |
| pytdx/mootdx | 补充 | 以上游声明为准 | 不分发 |
| LocalFile | 用户自有 CSV/Parquet | 用户自行确认 | 用户负责 |
| Synthetic | 开发/演示 | 项目生成，标注 SYNTHETIC | 可随仓库分发小样本 |

**仓库与演示包只含合成数据（标注 SYNTHETIC）与小体积录制 fixture；真实数据不入库、不再分发。**

## 运行时依赖
- C++：pybind11 (BSD-3)，Catch2 (BSL-1.0, test only)，Google Benchmark (Apache-2.0, bench only)。
- Python：numpy (BSD-3), pandas (BSD-3), pyarrow (Apache-2.0), duckdb (MIT), pydantic (MIT), FastAPI (MIT), uvicorn (BSD-3), typer (MIT), jinja2 (BSD-3), keyring (MIT)。
- UI：React (MIT), Vite (MIT), ECharts (Apache-2.0), KLineChart/lightweight-charts（许可证见 ADR）, Monaco (MIT), TanStack Table (MIT), Zustand (MIT)。
- **GPL/AGPL 不得进入分发包**；Backtrader (GPL-3.0) 仅作为 `dev` 可选、只在 `tests/reference` 交叉验证中使用，不随运行时/安装包分发。
- Electron/electron-builder (MIT) 仅 M10 桌面壳。

## SBOM
M10 生成 CycloneDX SBOM 并做许可证审计；新增依赖须在 `docs/DECISIONS.md` 记录。
### 公网行情源（本轮新增）

| 来源 | 用途 | 许可/条款 | 再分发 |
|---|---|---|---|
| 新浪财经公开行情（`vip.stock.finance.sina.com.cn` / `money.finance.sina.com.cn`） | 全市场 universe + 日线历史（主路径，免 token） | **非官方**公开网页接口，无 SLA、可能随时变更或限流；仅限个人研究自用，自设限速（≤2 并发、≥0.25s/请求、失败重试 2 次） | 不随仓库分发；抓取数据不得再分发/转售 |
| 腾讯行情（`web.ifzq.gtimg.cn` fqkline qfq） | 前复权收盘，用于复权因子/公司行为推导（可选） | 同上：非官方公开接口，无 SLA；仅个人研究自用 | 同上 |
| 东方财富公开接口（`push2.eastmoney.com` / `push2his.eastmoney.com`） | **备用**全市场日线（本机可能被限流：Empty reply） | 非官方公开网页接口，无 SLA；仅个人研究自用，自设限速 | 同上 |

- 网络能力默认关闭，仅在运行时显式设置 `QC_ALLOW_NETWORK=1`（或 provider 参数
  `allow_network=True`）后才会访问上述接口；默认测试与 UI 首启流程完全不联网。
- 仓库内 `tests/fixtures/sina/`、`tests/fixtures/eastmoney/` 只保留**小体积录制/派生样本**
  （1 页 universe、3 只股票若干日线、1 组构造的除权样本），用于离线测试；完整市场数据不入库、
  不随包分发。
- 数据仅为研究/模拟用途；任何结果须标注"历史表现不代表未来，不构成投资建议"。
