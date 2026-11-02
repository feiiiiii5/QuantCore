# QuantCore UI（M6 本地工作台）

React 19 + Vite + TypeScript（strict）+ TanStack Query/Table/Virtual + ECharts + Lightweight Charts + Monaco。
默认 zh-CN、系统字体、零 CDN；所有图表/编辑器依赖均来自本地 npm 包。

## 启动

后端（仓库根目录）：

```bash
uv run qc serve --port 8000 --open
```

前端开发（同源生产可直接用 `qc serve` 托管 `ui/dist`）：

```bash
pnpm -C ui install
pnpm -C ui dev          # http://127.0.0.1:5173，代理 /api /ws /health 到 8000
pnpm -C ui build        # tsc -b + vite build
pnpm -C ui preview      # 需要手动在设置页填后端地址
```

`qc serve --open` 的 `?token=` 会由 `src/main.tsx` 写入 localStorage 并从 URL 移除。
设置页留空 API 地址即同源；Token 仅保存在本机 localStorage，不写日志、不发第三方。

## 页面与能力

| 页面 | 能力 |
|---|---|
| 行情 `/` | overview 指数/涨跌分布/行业；证券本地过滤 + TanStack 虚拟表；lightweight-charts K 线、MA5/MA20/成交量开关、缩放/十字线；点击证券联动 K 线；URL `?code=` 与工作区记忆 |
| 选股 `/screener` | 预设/DSL、股票池、运行 `/api/screener/run`、虚拟表排序、CSV、localStorage 方案 |
| 策略 `/strategy` | 模板列表、JSON Schema 自动表单（number/integer/boolean/enum/min-max/默认值）、Monaco JSON、`/api/strategies/validate`、跳转回测 |
| 回测 `/backtest` | 模板/日期/资金/成交/滑点/费用/高级折叠；`POST /api/backtest` + `WS /ws/jobs/{id}?token=` 进度/取消；净值+回撤、指标、月度收益、费用、reasons、逐笔虚拟表、交易解释、点击交易联动 K 线、复现/报告 |
| 实验 `/experiments` | 列表、本地标签/笔记、详情、对比（≤6）、replay、HTML 报告、ZIP 导出、删除、空态 |
| 数据 `/data` | status/providers/snapshots/quality/storage、更新任务+进度、快照构建、真实路径复制/导入导出提示、三步首次向导 |
| 研究 `/research` | 因子 IC/RankIC/ICIR/分层/衰减、参数 sweep + 稳定性热力图、walk-forward、行业归因；接口 404 显示“未实现” |
| 设置 `/settings` | API 地址/Token、连接测试、主题/密度/涨跌色（红涨绿跌/绿涨红跌/色盲友好）、数据源/快照状态 |

App shell 含全局搜索（⌘K / Ctrl-K 聚焦、`/` 聚焦、Esc 关闭、Alt+1…8 切页）、状态栏（数据截止日/来源/任务/网络/后端版本）和工作区自动保存（路由、行情选择、选股草稿、回测草稿、实验标签/笔记）。

## 错误/空态约定

- `src/api/client.ts` 统一 `ApiError {status, detail}`；`request` 解析 `detail`，网络失败给出本地服务提示。
- 页面使用 React Query hooks（`src/api/queries.ts`）；加载/错误/空态/重试均有明确 UI。
- 研究 404 显示“未实现”而不是崩溃；WebSocket 失败自动退化为 HTTP 轮询，卸载时清理 socket/定时器。

## 测试

```bash
pnpm -C ui test     # Vitest：App shell、格式化、空态、ParamForm
pnpm -C ui build    # TypeScript strict + Vite
pnpm -C ui e2e      # Playwright（需要后端 + 本机 Chrome；默认 127.0.0.1:8123，token=test-token）
```

当前实测：`pnpm test` 10 passed（5 files）；`pnpm build` 通过；本地后端 + Chrome 下 Playwright 18 passed（行情/选股/回测/实验/数据/策略/设置/研究/onboarding/暗色/移动端/全局搜索/性能预算/模拟交易/组合/插件/稳健性/设置自检）。

## 与后端契约的偏差（不伪造）

后端 `docs/UI-API.md` 当前未提供以下字段/Live API，UI 采用明确降级而非 mock：

1. **基准**：`BacktestConfig` 无 benchmark 字段；表单显示禁用项“后端暂未支持”，不发送。
2. **调仓频率**：由模板参数控制（如 `buy_and_hold.rebalance`），独立表单字段未提供。
3. **持仓明细**：实验 result 只返回现金/市值/trades，无逐日持仓；结果页显示费用/交易/现金市值，不生成假持仓。
4. **逐笔收益贡献**：无逐笔已实现盈亏字段；交易解释显示方向/成交额/费用/reason，并明确不做“收益贡献”估算；方向现金流不是盈亏。
5. 研究进阶接口（Deflated Sharpe/PBO/成本敏感性等）未实现时后端 404，UI 显示未实现提示。

本项目仅研究与模拟，不包含真实下单；`BrokerGateway` 禁用。合成数据标 `SYNTHETIC`，历史表现不代表未来，不构成投资建议。
