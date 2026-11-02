# DESIGN-SPEC — QuantCore UI 设计规范（v2 / Apple 设计语言）

> 状态：2026-11-02 · v2 重构轮。本规范是前端并行重构的唯一契约。
> 视觉与交互基准：Apple Human Interface Guidelines（Clarity / Deference / Depth）；
> 工程基准：优先使用 GitHub 上成熟开源方案，不重复造轮子。

## 0. 技术栈（成熟方案优先）

| 领域 | 方案 | 说明 |
|---|---|---|
| UI 无障碍原语 | `@radix-ui/react-*`（Dialog / DropdownMenu / Popover / Select / Switch / Tabs / ToggleGroup / Tooltip） | headless + WAI-ARIA，Open AI/shadcn 生态事实标准 |
| 动效 | `framer-motion` | 页面转场、弹层、列表进场；尊重 `prefers-reduced-motion` |
| 通知 | `sonner` | 替代自研 Toast，支持队列/关闭/位置 |
| 命令面板 | `cmdk` | ⌘K 面板，模糊搜索 + 键盘导航 |
| 移动端抽屉 | `vaul` | iOS 风格 bottom sheet |
| 图表 | `lightweight-charts`（TradingView 开源） | K 线 / 净值 / 柱状；移除 echarts |
| 表格/虚拟滚动 | `@tanstack/react-table` + `@tanstack/react-virtual` | 已引入，统一走它 |
| 数据请求 | `@tanstack/react-query` | 已引入 |
| 路由 | `react-router-dom` | 已引入 |
| 图标 | `lucide-react` | 统一 1.5px stroke、18/16/14px |

后端对应（本轮）：`exchange-calendars`（XSHG 真实交易日历，替代星期几启发式）、FastAPI/Pydantic/httpx/DuckDB/pyarrow（已有成熟栈）。

## 1. Apple 设计原则（本项目的落地方式）

1. **Clarity 清晰**：一屏只有一个主角。大标题 + 一句说明 + 一个主 CTA；数字用大号(28–34px)、字重 600、tabular-nums；标签 12–13px 次级灰。
2. **Deference 退让**：内容优先，界面元素不与数据抢注意力。卡片用 1px 发丝线 + 极浅阴影，不用重描边；装饰性图形一律删除。
3. **Depth 层次**：用材质(半透明毛玻璃)、阴影、层级动效表达前后关系；弹层从触发点/屏幕边缘出现，背景降低透明度并轻微缩放。
4. **Typography 排版**：系统字体栈（SF Pro / PingFang SC / Segoe UI），不引入远程字体；标题字距收紧（-0.02em）；正文 13–15px；行高 1.5；正文宽度不超过 72ch。
5. **Rhythm 节奏**：8pt 网格；卡片内 16–20px、卡片间 16px、页面 24–32px；分组之间留白大于组内。
6. **Color 克制**：中性灰为主（页面 #F5F5F7 / 深色 #000），强调色仅用于主操作、选中、焦点（系统蓝）；涨跌红绿是唯一语义色；其余状态用系统黄/红/绿的低饱和变体。
7. **Materials 材质**：顶栏/底栏/侧栏用 `backdrop-filter: saturate(180%) blur(20px)` + 半透明底色；深色模式提高层级亮度（#1C1C1E→#2C2C2E）。
8. **Motion 动效**：时长 120–260ms；转场 `cubic-bezier(0.32,0.72,0,1)`；按下 scale(0.98)；不做无意义的循环动画；reduced-motion 全部关闭。
9. **Craft 细节**：hover/active/disabled/focus-visible 四态齐全；空态有下一步动作；loading 用骨架不转圈；错误可重试；所有交互元素 ≥32px 高、可键盘操作。
10. **Accessibility 无障碍**：对比度 ≥4.5:1；焦点环 3px 系统蓝 40% 透明度；aria-label/role 完整；移动端 44px 触控目标。

## 2. Design Tokens（重写 `styles/tokens.css`；深浅色同名变量）

颜色（浅色 / 深色）：
```
--bg            #F5F5F7 / #000000        页面底色
--surface       #FFFFFF / #1C1C1E        卡片
--surface-2     #FFFFFF / #2C2C2E        浮起/输入框
--surface-3     #F0F0F4 / #3A3A3C        表头/次级块
--material      rgba(255,255,255,.72) / rgba(28,28,30,.72)   毛玻璃顶栏
--text          #1D1D1F / #F5F5F7
--text-2        #6E6E73 / #98989D
--text-3        #86868B / #7C7C80
--separator     rgba(60,60,67,.12) / rgba(255,255,255,.12)   发丝线
--accent        #0071E3 / #0A84FF        系统蓝（主操作/链接/焦点）
--accent-press  #0062C4 / #409CFF
--accent-weak   rgba(0,113,227,.10) / rgba(10,132,255,.16)
--up            #E5342B / #FF6B63        涨（默认红涨）
--down          #00A35C / #30D158        跌（默认绿跌）
--warn          #B25000 / #FFD60A
--danger        #D70015 / #FF453A
--ok            #248A3D / #30D158
--info          #0071E3 / #0A84FF
```

字体：
```
--font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
--font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
--fs-caption2 11/13 · --fs-caption 12/16 · --fs-footnote 13/18 · --fs-subhead 15/20
--fs-body 15/22 · --fs-headline 17/22 · --fs-title3 20/25 · --fs-title2 24/30
--fs-title1 28/34 · --fs-large 34/41
--fw-regular 400 · --fw-medium 500 · --fw-semibold 600 · --fw-bold 700
```

间距 / 圆角 / 阴影 / 动效：
```
--sp-1..--sp-10: 2/4/6/8/12/16/20/24/32/48px
--radius-xs 6 · --radius-sm 8 · --radius 12 · --radius-lg 16 · --radius-xl 22 · --radius-pill 999
--shadow-1 0 1px 2px rgba(0,0,0,.05) · --shadow-2 0 8px 28px rgba(0,0,0,.08)
--shadow-pop 0 20px 60px rgba(0,0,0,.18) · --shadow-sheet 0 -12px 48px rgba(0,0,0,.16)
--blur-material: saturate(180%) blur(20px)
--ease-out: cubic-bezier(0.32,0.72,0,1) · --ease-in-out: cubic-bezier(0.4,0,0.2,1)
--dur-1 120ms · --dur-2 180ms · --dur-3 260ms · --dur-4 360ms
```

密度：`[data-density="compact"]` 缩小行高与内边距（控件 28px/行 32px）；默认舒适（控件 36px/行 40px）。
主题/密度/涨跌色（由 `lib/appearance.ts` 写在 `<html>` 上）：`html[data-theme="light|dark"]`、`html[data-density="comfortable|compact|spacious"]`、`html[data-color-mode="red-up|green-up|color-blind"]`。

## 3. 布局（重写 `styles/layout.css`）

```
┌──────────────────────────────────────────────────────────────────────┐
│ AppBar 52px（毛玻璃）：品牌 · 实时指数条 · ⌘K 搜索 · 市场状态 · 新手 · 主题 │
├──────┬───────────────────────────────────────────────────────────────┤
│ Rail │ Content（最大 1560px 居中，padding 28/32px）                  │
│ 64px │  PageHeader：34px 大标题 + 15px 说明 + actions                 │
│      │  卡片网格：12 列，gap 16px                                    │
├──────┴───────────────────────────────────────────────────────────────┤
│ StatusBar 28px（毛玻璃）：数据源 · 快照 · 引擎 · 任务 · 免责              │
└──────────────────────────────────────────────────────────────────────┘
```
- ≥1280：售后 Rail 常驻 + 12 列；1024–1279：两栏；<1024：Rail 收起为底部 TabBar（44px 触控），页面单栏。
- 滚动：内容区独立滚动，AppBar/StatusBar 固定；页面切换后滚动复位。

## 4. 组件契约（`ui/src/components/`，统一从 `index.ts` 导出）

### 4.1 基础原语（新）
| 组件 | props | 说明 |
|---|---|---|
| `Button` | variant: primary/secondary/ghost/danger; size: sm/md/lg; loading; icon; iconRight | 所有按钮统一走它 |
| `Field` | label, hint, error, required, children | 表单行 |
| `Input` / `Textarea` / `Select` | 原生属性 + `invalid` | Select 可用 Radix Select |
| `Switch` | checked, onChange, label, description, disabled | Radix Switch |
| `Segmented` | items, value, onChange, size | Radix ToggleGroup |
| `Tabs` | items, value, onChange, ariaLabel | Radix Tabs |
| `Dialog` | open, onOpenChange, title, description, footer, size | Radix Dialog + framer-motion |
| `Sheet` | open, onOpenChange, side: right/bottom, title, footer | 桌面右滑 / 移动端 vaul bottom |
| `Menu` | trigger, items（label/icon/danger/onSelect/separator） | Radix DropdownMenu |
| `Tooltip` | content, children, side | Radix Tooltip |
| `Popover` | trigger, children, align | Radix Popover |
| `Toaster` | — | sonner 挂载点；`notify()` 适配器保持旧 API |
| `ProgressBar` | value, tone, label | 进度条 |
| `List` / `ListRow` | 分组列表 | 设置/数据页的 Apple 分组列表 |
| `Callout` | tone: info/warn/danger/success, title, children, action | 提示块 |
| `PageHeader` | title, subtitle, actions, breadcrumb | 页头大标题 |

### 4.2 业务组件（保留 API，重做视觉）
`Panel/Card`、`StatTile`、`DataTable`、`ChartCard`、`Chart`（lightweight-charts）、`KLineChart`、`EmptyState`、`Skeleton`、`StepList`、`Badge/Tag`、`SectionHeader`、`Toolbar`、`MetricPill`、`QuoteRow`、`Sparkline`、`CommandPalette`（cmdk）、`AppBar`、`Rail`、`MobileTabBar`、`StatusBar`、`Onboarding`。

### 4.3 CSS 类契约（页面必须复用，禁止自造视觉）
```
布局：.page .page-header .page-title .page-sub .page-actions .grid .grid-2 .grid-3 .grid-4
      .col .row .stack .split .spacer .scroll-y
卡片：.card .card-head .card-title .card-sub .card-body .card-foot .card-actions
按钮：.btn .btn-primary .btn-secondary .btn-ghost .btn-danger .btn-sm .btn-lg .icon-btn
表单：.field .field-label .field-hint .input .select .textarea .checkbox .radio
分段：.segmented .segmented-item[aria-checked]
标签页：.tabs .tab[aria-selected]
表格：.table-wrap table thead th tbody td .num .table-row-hover .table-empty
徽章：.badge .badge-ok .badge-warn .badge-danger .badge-info .pill
数字：.kpi .kpi-value .kpi-label .kpi-delta .delta-up .delta-down
列表：.list .list-row .list-row-title .list-row-sub .list-row-action .list-sep
空态/骨架：.empty .empty-icon .empty-title .empty-hint .skeleton .skeleton-line
弹层：.dialog-overlay .dialog-panel .sheet-panel .menu-content .tooltip-content .popover-content
图表：.chart-card .chart-body .chart-legend .chart-empty
提示：.callout .callout-info .callout-warn .callout-danger .callout-success
```

## 5. 视觉与交互细节（验收时逐条检查）

- 顶栏：52px，`--material` + 底部发丝线；滚动后阴影增强（scrollY>8）。
- 页面标题：34px/600/-0.02em；说明 15px `--text-2`；主 CTA 在标题右侧同一基线。
- 卡片：`--surface` + 发丝线 + `--radius-lg` + `--shadow-1`；hover 时阴影升到 `--shadow-2`，不做位移。
- 数字：28px/600 tabular-nums；涨跌色只在数值与箭头，不铺满背景。
- 表格：40px 行高；表头 12px 大写?（中文不转大写）`--text-3`；行 hover `--surface-3`；选中行 3px accent 左边线。
- 弹层：overlay `rgba(0,0,0,.28)` + blur(2px)；panel 从 scale(.96)/translateY(8px) 进入 180ms。
- 通知：sonner 右下/顶部居中，圆角 12、毛玻璃、图标 + 标题 + 描述。
- 命令面板：居中 560px，顶部输入 44px，分组标题 11px，选中行 accent-weak。
- 移动端：底部 TabBar 5 个入口（今日/行情/回测/数据/我的），使用 vaul sheet 打开二级导航。
- 焦点：`:focus-visible` 3px accent 30% ring；不使用浏览器默认 outline。
- 加载：骨架屏形状与实际内容一致；首屏不闪白（背景色与卡片占位）。

## 6. 页面规格（首屏必须回答的问题）

### 6.1 今日 /today
市场状态带（4 指数 + 涨跌 + sparkline）→ 主 CTA「开始一次研究」→ 我的自选 → 新手 4 步清单 → 最近研究（结论徽章）→ 数据体检摘要。大标题 34px + 一句「今天先做什么」。

### 6.2 行情 /market
证券搜索/自选列表（左）→ 报价 Hero（大号价格 + 涨跌 + 读数网格）→ K 线主图（lightweight-charts，切换分时/日线）→ 右侧：实时状态、涨跌分布、数据体检入口。离线明确标注。

### 6.3 回测 /backtest
三步式（1 选策略 2 数据与区间 3 运行）用 stepper；模板卡片带白话说明；运行按钮 sticky；结果页结论 banner + 4 个 KPI + Tabs（净值/回撤/月度/交易/解释）+ 数据体检徽章。

### 6.4 数据 /data
数据体检 Hero（状态 + 覆盖率 + 缺口）→ 体检项分组列表（Apple Settings 风格）→ 真实数据导入（Sina/Eastmoney/Tushare/本地，网络关闭时置灰并给开启指引）→ 快照列表 → 合成示例。

### 6.5 模拟 /paper
账户摘要（权益/收益/持仓/待成交）→ 持仓/委托/成交表 → 下单面板（Sheet 或右侧卡）→ 权益曲线 → 多策略组合。

### 6.6 研究 /research
Tabs（因子/扫描/滚动/归因/稳健性）→ 表单行 → 结论 Callout（一句话判断）→ 图表/表格。

### 6.7 选股/策略/实验/设置
选股：表达式 + chips + 结果表 + 带回测；策略：模板卡片 + 插件列表 + 编辑器 Sheet；实验：卡片列表 + 对比 Sheet；设置：Apple 分组列表（连接/数据与网络/外观/新手/自检/关于）。

## 7. 新手模式与实时规则（沿用 v1）
- 新手模式默认开，`localStorage qc_beginner`；隐藏高级参数、术语 tooltip、每页下一步建议、空态优先"一键示例"。
- 实时状态：实时（绿点+时间）/休市（灰点+最近收盘）/离线（黄点+快照日期）；网络未开启不得发起请求；价格变化 flash ≤200ms。

## 8. 验收
- `pnpm -C ui build` / `pnpm -C ui test` 通过；Playwright 全部通过。
- 1440×1000 与 390×844 无横向溢出；深浅色、色盲、紧凑密度逐一截图。
- 每页 loading/empty/error 三态；键盘可完成：⌘K → 跳页、Tab 焦点、Esc 关闭。
- 截图更新 `docs/screenshots/`；本规范与实际实现一致。
