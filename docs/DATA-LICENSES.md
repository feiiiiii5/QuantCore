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
