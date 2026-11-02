# UI — 交互与页面（v2 / Apple 设计语言）

前端 `ui/`：React 19 + Vite + TypeScript。设计规范见 `docs/DESIGN-SPEC.md`（v2，Apple HIG），
产品理念见 `docs/PRODUCT.md`。工程原则：**优先使用 GitHub 上成熟开源方案**，不重复造轮子。

```
pnpm -C ui dev     # Vite dev（/api /ws /health 代理到 127.0.0.1:8000）
pnpm -C ui build   # tsc -b + vite build → ui/dist，由 qc serve 同源托管
pnpm -C ui test    # vitest（jsdom）
pnpm -C ui exec playwright test   # 或 make e2e（隔离 qc serve + Chrome）
node ui/scripts/ui-audit.mjs      # 本地截图/溢出/console/a11y 审计（需 QC_BASE/QC_TOKEN）
```

## 技术栈（成熟方案）

| 领域 | 方案 | 用途 |
|---|---|---|
| 无障碍原语 | `@radix-ui/react-*` | Dialog/Sheet/Menu/Popover/Select/Switch/Tabs/ToggleGroup/Tooltip（WAI-ARIA）|
| 动效 | `framer-motion` | 页面转场、弹层、通知；`prefers-reduced-motion` 关闭 |
| 通知 | `sonner` | 统一 toast；保留 `lib/notify.ts` 旧 API 与桌面通知 |
| 命令面板 | `cmdk` | ⌘K 模糊搜索 + 键盘导航 |
| 移动抽屉 | `vaul` | iOS 风格 bottom sheet（更多导航）|
| 图表 | `lightweight-charts`（TradingView）| K 线、净值/回撤、月度柱状；已移除 echarts |
| 表格/虚拟滚动 | `@tanstack/react-table` + `@tanstack/react-virtual` | 选股/交易/持仓等大表 |
| 数据请求 | `@tanstack/react-query` | 缓存、轮询、任务进度 |
| 路由/状态 | `react-router-dom` + `zustand` | 路由、UI/工作区状态 |
| 图标/样式 | `lucide-react` + 设计 token CSS | 统一 1.5px 图标；不引入远程字体/CDN |

## 信息架构（IA）

| 组 | 路由 |
|---|---|
| 今日 | `/today`（默认；`/` 重定向） |
| 行情 | `/market` |
| 研究 | `/screener` `/strategy` `/backtest` `/experiments` `/research` |
| 模拟 | `/paper` |
| 数据 | `/data` |
| 设置 | `/settings` |

## 应用外壳（Apple 风格）

- **AppBar 52px**：毛玻璃材质 + 滚动阴影；品牌 · 实时指数条（实时）/「实时未开启」入口（离线）· ⌘K · 新手模式 Switch · 主题切换。
- **Rail 64px**：分组图标导航（今日/行情/研究×5/模拟/数据/设置）；当前页高亮；Alt+1…9 / Alt+0 与 `g`+数字快捷跳页。
- **StatusBar 28px**：实时状态 · 数据源 · 快照日期 · 引擎 · 任务 · 网络 · 免责声明。
- **MobileTabBar（<1024px）**：今日/行情/回测/数据/我的 5 入口；「我的」用 vaul sheet 展开二级导航。
- **CommandPalette（⌘K / Ctrl-K / `/`）**：跳页、证券、命令（主题/新手模式/引导/实时设置/数据体检）；cmdk 分组 + 键盘。
- **页面转场**：framer-motion 200ms（`cubic-bezier(0.32,0.72,0,1)`），路由切换滚动复位，reduced-motion 关闭。
- **跳转链接**：`skip-link` 键盘可达；焦点环 3px accent 30%。

## 设计系统

- 全部 tokens 在 `ui/src/styles/tokens.css`（Apple 浅/深色、毛玻璃 material、hairline、34px 标题阶梯、8pt 网格、
  radius/shadow/motion/density；`data-theme` / `data-density` / `data-color-mode` 三套选择器；保留 v1 别名）。
- 样式拆分：`styles/{tokens,base,layout,components,business,overlays,views}.css` + `styles.css` 汇总；单文件 <500 行。
- 组件（`ui/src/components/index.ts`）：
  - 原语：`Button` `Field` `Input` `Textarea` `Select` `Switch` `Segmented` `Tabs` `PageHeader` `Callout`
    `List/ListRow/ListSep` `ProgressBar` `Dialog` `Sheet` `Menu` `Tooltip` `Popover` `Toaster`。
  - 业务：`Panel/Card` `StatTile` `DataTable` `VirtualTable` `Chart` `KLineChart` `ChartCard` `Sparkline`
    `EmptyState` `Skeleton` `StepList` `Badge/Tag` `SectionHeader` `Toolbar` `MetricPill` `QuoteRow`
    `CommandPalette` `AppBar` `Rail/MobileTabBar` `StatusBar` `Onboarding` `ParamForm` `RobustnessPanel`
    `PaperPortfolioPanel` `ErrorBoundary`。
- 图表使用 `Chart` 声明式 API：`<Chart series={[{ kind: "area", data, title }]} />`；`time` 支持 YYYYMMDD/ISO/epoch。
- 三态：每个数据区块有 loading（骨架）/ empty（带下一步）/ error（重试）；实时关闭显示 stale 标注。
- 无障碍：`:focus-visible`、aria-label/role、tabular-nums、对比度 ≥4.5:1、reduced-motion 关闭动画。

## 页面

### 今日 `/today`
市场状态 4 指数（实时优先/离线快照 + Sparkline）→ 主 CTA「开始一次研究」→ 我的自选 → 新手 4 步清单 →
最近研究（结论徽章）→ 数据体检摘要。

### 行情 `/market`
指数带 → 证券列表（全部/自选 + 搜索，虚拟滚动）→ K 线（MA5/MA20/成交量/分钟切换）→ 实时读数网格 →
涨跌分布 → 数据体检入口；实时开启显示绿点/更新时间，关闭显示「离线快照」与开启指引。

### 研究（选股/策略/回测/实验/研究）
- 回测：三步 wizard（白话策略卡 → 数据与区间 → 运行）→ 结论 banner + 4 KPI + Tabs（净值与回撤双 pane / 月度 / 交易明细 / 交易解释+K线）+ 数据体检徽章。
- 研究：5 tab（因子诊断/参数扫描/滚动验证/归因/稳健性）；先结论后图表；参数扫描用 heatmap 工具类。
- 选股：条件/预设 → 虚拟表格 → 「用这个结果回测」；策略：模板卡 + JSON Sheet + 插件；实验：卡片 + 对比 Sheet。

### 模拟 `/paper` / 数据 `/data` / 设置 `/settings`
- 模拟：会话 → 2×2 KPI → 权益曲线 → 持仓/委托/成交 → 下单面板 → 提醒/组合；partial 显示「成交/委托」。
- 数据：体检 hero（覆盖率/缺口/准确性 + 检查列表）→ 导入真实数据（网络关闭明确说明）→ 快照表（质量报告 Dialog）→ V2 数据集。
- 设置：Apple 分组列表（本地服务/数据与网络/外观/新手模式/自检/关于）。

## 实时行情
- 服务端 `QC_ALLOW_NETWORK=1` 才联网；测试全程录制 fixture。
- 实时报价走共享 WebSocket：`lib/liveStream.ts` 每个代码集只开一个 `/ws/live` 连接（退避重连），
  写入 react-query 缓存；失败自动回退 HTTP 轮询（15s），不阻塞页面。
- 状态：`实时`（绿点 + 更新时间）/ `休市`（灰点 + 最近收盘）/ `离线`（黄点 + 快照日期）；价格变化 ≤200ms。

## 验证
- `pnpm -C ui exec tsc -p tsconfig.json`、`pnpm -C ui test`、`pnpm -C ui build` 全绿。
- `make e2e`：18 条 Playwright（新首页/行情/回测任务/数据体检/命令面板/移动端/暗色/插件/模拟…）。
- `node scripts/ui-audit.mjs`：10 路由 + 移动端 + 暗色，检查 status/overflow/console/h1/aria/图表数。
