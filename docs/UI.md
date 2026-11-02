# UI — 交互与页面（重构轮）

前端 `ui/`：React 19 + Vite + TypeScript；设计规范见 `docs/DESIGN-SPEC.md`，产品理念见 `docs/PRODUCT.md`。
构建：`pnpm -C ui build`；开发：`pnpm -C ui dev`（Vite 代理 `/api` `/ws` `/health` 到 `127.0.0.1:8000`）。
生产：`qc serve` 同源托管 `ui/dist`，无 CORS、无 CDN；Monaco/ECharts/Lightweight Charts 全部本地 bundle。
仅研究与模拟，不连接券商、不下真实单；所有结果页与报告保留"历史表现不代表未来，不构成投资建议"。

## 信息架构（IA）
一级导航 6 组（左侧 68px 图标 rail；≤900px 变底部 tab）：

| 组 | 路由 |
|---|---|
| 今日 | `/today`（默认；`/` 重定向到 `/today`） |
| 行情 | `/market` |
| 研究 | `/screener` `/strategy` `/backtest` `/experiments` `/research` |
| 模拟 | `/paper` |
| 数据 | `/data` |
| 设置 | `/settings` |

## 应用外壳
- **AppBar（56px）**：品牌 · 实时指数条（上证/深成/创业板/科创50，涨跌色 + 实时/休市/离线状态点）· ⌘K 命令面板 · 新手模式开关 · 主题切换。
- **Rail（68px）**：图标 + 文字分组导航；当前页高亮；Alt+1…9 / Alt+0 与 `g`+`数字` 跳页。
- **StatusBar（28px）**：实时状态 · 数据源 · 快照日期 · 引擎 · 任务 · API 地址 · 免责声明。
- **CommandPalette（⌘K / Ctrl-K / `/`）**：跳页、搜索证券（快照列表）、运行命令（主题/新手模式/新手引导/实时设置/数据体检）。
- 新手引导弹窗改为 2 步（生成示例数据 → 跑示例回测），由首页 CTA 或命令面板打开。

## 设计系统
- tokens 全部在 `ui/src/styles/tokens.css`（浅/深色、紧凑密度、红涨/绿涨/色盲蓝橙）；组件与页面只消费 `var(--*)`，禁止硬编码颜色。
- 样式拆分：`styles/{tokens,base,layout,components,overlays,views,legacy}.css`，`styles.css` 只做 @import；单文件 <500 行。
- 通用组件（`ui/src/components/index.ts` barrel）：Panel、StatTile、SectionHeader、Toolbar、Segmented、Badge/Tag、DataTable、Sparkline、ChartCard、EmptyState、Skeleton、StepList、Tabs、MetricPill、QuoteRow、CommandPalette；既有组件（Chart、KLineChart、VirtualTable、ParamForm、StatePanel、MetricCard、RobustnessPanel、PaperPortfolioPanel、Toasts、ErrorBoundary、GlobalSearch、StatusBar）保持导出名与 props 兼容。
- 三态约定：每个数据区块必须实现 loading（骨架）/ empty（带下一步）/ error（重试 + 提示）；实时关闭或数据过期显示 stale 标注。
- 无障碍：`:focus-visible` 焦点环、aria-label、tabular-nums、`prefers-reduced-motion` 关闭动画。

## 页面

### 今日 `/today`
- 市场状态带：四大指数（实时优先，关闭实时时用最近快照 + 明确状态点）、涨跌色、迷你走势、休市/离线提示。
- 我的自选：6 位代码添加/移除；实时开启时显示实时报价，否则显示快照报价；空态引导去行情页。
- 新手进度：后端 `/api/onboarding` 四步（生成示例数据 → 跑第一个回测 → 看懂结果 → 数据体检），完成打勾；不可用时回退到静态步骤。
- 最近研究：最近 6 个实验卡片（策略、总收益/Sharpe/最大回撤、SYNTHETIC 与数据体检徽章、时间），空态给"一键示例"。
- 数据体检摘要：状态徽章 + 覆盖率/标的数/交易日/缺口 + warn/fail 检查项；失败醒目提示。
- 主 CTA「开始一次研究」→ `/backtest`；新手模式显示"怎么看这一页"三句话说明。

### 行情 `/market`
- 指数卡（实时优先）→ 证券搜索/自选/全部列表 → K 线主图（MA5/MA20/成交量/分钟切换）→ 右侧实时读数（现价、涨跌、今开/高/低/昨收、成交额、振幅、涨跌停、换手、更新时间）。
- 实时开启：绿点 + 最后更新时间；未开启：黄色"离线快照" + 去设置开启提示；实时失败回退快照并提示。
- 底部/右栏：数据源、快照 ID 与日期、数据体检徽章与覆盖率；保留证券资料、PIT 财务、涨跌分布与 SYNTHETIC 标注。
- 「加入自选」写入本地 watchlist；「开始一次研究」带代码去回测页。

### 研究工作台（选股/策略/回测/实验/研究）
- 结论先行、三态齐全；新手模式隐藏高级参数并给"下一步建议"；结果带数据体检/可信度徽章。细节见各页面实现与 DESIGN-SPEC §6.3。

### 模拟 `/paper` / 数据 `/data` / 设置 `/settings`
- 模拟：会话 → 持仓/委托/成交/权益曲线 → 下单面板；partial 状态显示"部分成交 成交/委托"；明确不连接券商。
- 数据：数据体检优先 → 导入真实数据（网络默认关，开启需显式确认）→ 快照列表 → 合成示例入口（SYNTHETIC）。
- 设置：服务/Token、实时行情开关、自检、主题/密度/涨跌色、新手模式、免责声明。

## 新手模式
- 默认开启，状态存 localStorage `qc_beginner`（`ui/src/store/ui.ts`：`useBeginner()` / `setBeginner()`）；AppBar 与设置页可切换。
- 开启时：隐藏高级参数、术语白话解释、突出"下一步"、空态优先"一键示例"、结果页"怎么看这个结果"。

## 实时行情规则
- 网络能力只在运行时显式开启（服务端 `QC_ALLOW_NETWORK=1`）；测试用录制 fixture，不联网。
- 状态：`实时`（绿点 + 更新时间）/ `休市`（灰点 + 最近收盘）/ `离线`（黄点 + 快照日期）；未开启时全站不发起行情网络请求。
- 数据源、延迟、最后更新时间在行情页与 StatusBar 可见；价格变化用 ≤200ms 轻闪动画，尊重 reduced-motion。

## 验证
- `pnpm -C ui exec tsc -p tsconfig.json`、`pnpm -C ui test`、`pnpm -C ui build`。
- Playwright（Lead 统一更新选择器）：新首页 `/today`、行情 `/market`、⌘K 命令面板、新手模式开关、实时/离线徽章为新增锚点。
- 关键 DOM：`.app-shell/.appbar/.rail/.statusbar/.panel/.stat-tile/.badge/.segmented/.step-list/.tabs/.quote-row/.research-card/.readings-grid`；首页标题「今日」、行情标题「行情」。
