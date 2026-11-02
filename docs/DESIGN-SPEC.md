# DESIGN-SPEC — QuantCore UI 设计规范（重构轮）

> 状态：2026-11-02。本规范是并行 UI 重构的统一契约：token、布局、组件、页面规格。
> 所有新代码必须使用 token 与通用组件，不得硬编码颜色/间距；页面级样式放 `ui/src/pages/*.css`。

## 1. 设计原则

1. **结论先行**：页面第一屏先给状态/结论，控件后置；顶部固定"状态带"。
2. **一眼可读**：关键数字大、标签小；红涨绿跌（可切绿涨红跌/色盲友好）；数字用 tabular-nums。
3. **一步一动作**：每屏一个主 CTA（primary），其余降级为 ghost/secondary。
4. **渐进披露**：新手模式默认开；高级参数折叠；专业模式可展开全部。
5. **诚实标注**：数据源/快照日期/体检状态/免责声明常驻可见，不静默降级。
6. **少即是多**：去掉无信息的空白卡片；每个区域必须承载信息或动作。
7. **键盘优先**：⌘K 命令面板、/ 搜索、g+数字跳页、Esc 关闭。
8. **无障碍**：焦点环、aria-label、对比度 ≥ 4.5:1、prefers-reduced-motion 关闭动画。

## 2. 信息架构（IA）

一级导航收敛为 5 组（侧栏分组 + 顶部状态带）：

```
首页 Today      —— 市场状态、自选、新手下一步、最近研究、数据体检
行情 Market     —— 指数/自选/证券搜索/K线/读数（实时优先，离线回退快照）
研究 Workbench  —— 选股 · 策略 · 回测 · 实验 · 研究（二级 tab 或子导航）
模拟 Paper      —— 会话、持仓、委托/成交（部分成交标记）
数据 Data       —— 数据体检、真实数据导入、快照、覆盖率
设置 Settings   —— 服务/token、网络与实时开关、主题/密度/新手模式、自检
```

路由兼容：保留现有 `/screener /strategy /backtest /experiments /research /paper /data /settings`，
新增 `/today`（首页，默认 `/` 重定向到 `/today`；旧 `/` 行情保留为 `/market`）。

## 3. 布局

```
┌─────────────────────────────────────────────────────────────────────┐
│ AppBar: brand │ 指数实时条 │ ⌘K 搜索 │ 市场状态 ● │ 新手模式 │ 主题 │
├──────┬──────────────────────────────────────────────────────────────┤
│ Rail │ Header: 页面标题 + 一句说明 + 主 CTA                        │
│ 56px │ Content: 12 列网格（桌面），卡片/表格/图表                    │
│      │                                                              │
├──────┴──────────────────────────────────────────────────────────────┤
│ StatusBar: 数据源 · 快照日期 · 引擎 · 任务 · 免责声明                 │
└─────────────────────────────────────────────────────────────────────┘
```

- 断点：≥1280 三栏网格；1024–1280 两栏；<1024 单栏 + 底部 tab；移动端无横向溢出。
- 内容最大宽度 1600px，居中；页面 padding 24px（紧凑 16px）。
- 固定顶部 AppBar（56px）+ 底部 StatusBar（28px），内容区独立滚动。

## 4. Design Tokens（`styles.css` `:root` 定义，深浅色同名变量）

颜色：
```
--bg, --bg-elev, --surface, --surface-2, --border, --border-strong
--text, --text-2, --muted, --primary, --primary-weak, --on-primary
--up, --up-weak, --down, --down-weak, --flat
--ok, --warn, --danger, --info   (+ 对应 weak 背景)
--focus-ring
```
- 涨跌语义只走 `--up/--down`；禁止用 primary 表达涨跌。
- 深浅色两套；色盲模式把 `--up/--down` 替换为蓝/橙。
字体：
```
--font-sans: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif
--font-mono: ui-monospace, SFMono-Regular, Menlo, monospace
字号阶梯：--fs-11 / --fs-12 / --fs-13 / --fs-14 / --fs-16 / --fs-20 / --fs-28 / --fs-36
行高：--lh-tight 1.2 / --lh-normal 1.5
```
间距/圆角/阴影/动效：
```
--sp-1..--sp-8 = 4/8/12/16/24/32/48/64
--radius-sm 6 / --radius 10 / --radius-lg 14 / --radius-pill 999
--shadow-1 / --shadow-2 / --shadow-pop
--dur-1 120ms / --dur-2 200ms / --ease standard
```
- 卡片：`surface + 1px border + radius-lg`，无重阴影；hover 仅提升 border/text。
- 数字：`font-variant-numeric: tabular-nums`，金额/百分比统一保留 2 位（大数用 亿/万）。

## 5. 组件契约（`ui/src/components/`，统一导出）

| 组件 | 用途 | 关键 props |
|---|---|---|
| `Panel` | 通用卡片容器 | title, subtitle, actions, dense, tone |
| `StatTile` | 单个关键数字 | label, value, delta, trend, hint, tone, size |
| `SectionHeader` | 区块标题 | title, hint, actions |
| `Toolbar` | 页内筛选/操作条 | children, sticky |
| `Segmented` | 模式切换 | options, value, onChange |
| `Badge` / `Tag` | 状态徽章 | tone: ok/warn/danger/info/neutral, children |
| `DataTable` | 表格（排序/空态） | columns, rows, dense, onRowClick |
| `Sparkline` | 迷你走势 | data, tone |
| `ChartCard` | 图表容器 + 空态 | title, actions, height |
| `EmptyState` | 空态 | title, hint, action |
| `Skeleton` | 骨架屏 | rows |
| `StepList` | 新手步骤 | steps, current, onAction |
| `CommandPalette` | ⌘K 命令面板 | open, onClose, items |
| `Tabs` | 二级导航 | items, value, onChange |
| `MetricPill` | 结果页指标 | label, value, hint, tone |

状态覆盖：每个数据区块必须实现 loading（骨架）、empty（带下一步动作）、error（重试 + 提示）、stale（实时关闭/数据过期）。

## 6. 页面规格（首屏必须回答的问题）

### 6.1 首页 Today（新增）
1. 市场状态带：上证/深成/创业板/科创50 实时卡（涨跌幅 + 迷你分时/Sparkline），休市显示最近收盘 + "休市"。
2. 我的自选：报价表（涨跌、成交额、异动标记），未设置时显示"添加自选"引导。
3. 新手进度：3–5 步清单（生成示例数据 → 跑第一个回测 → 看结果 → 试试参数），完成后折叠。
4. 最近研究：研究卡片（结论 + 体检徽章 + 时间），空态给"一键示例"。
5. 数据体检摘要：覆盖率/缺口/最近导入；不通过时黄色/红色提示。
6. 主 CTA：「开始一次研究」。

### 6.2 行情 Market
搜索/自选/指数 → K 线主图（轻量图表，可切指标）→ 右侧读数（现价、涨跌、成交、振幅、涨跌停）→ 底部（数据源/快照日期/体检）。实时开启时显示 ● 实时 + 更新时间；关闭时明确"离线快照"。

### 6.3 研究工作台（选股/策略/回测/实验/研究）
- 选股：一句话选股条件 + 模板 chips → 结果表 → 一键回测。
- 策略：模板卡片（白话说明 + 风险）→ 参数（新手隐藏高级）→ 校验/保存。
- 回测：三步式（策略 → 数据与区间 → 运行）；运行中进度；结果页结论先行（4 个 StatTile）+
  可信度徽章 + Tab（净值/回撤/交易/解释）+ 下一步。
- 实验：卡片/表格列表 + 对比（最多 4 个）+ replay/导出。
- 研究：因子 IC/分层/扫描/稳健性，结论优先（先给"这个因子有没有用"的一句话判断）。

### 6.4 模拟 Paper
会话卡片（权益/收益/持仓数/待成交）→ 详情（持仓/委托/成交/权益曲线）→ 下单面板（数量/方向/类型，新手默认市价 + 提示 T+1）。partial 状态显示"部分成交 成交/委托"。

### 6.5 数据 Data
数据体检优先（状态徽章 + 覆盖率 + 缺口 Top N + 修复建议）→ 导入真实数据（东方财富免 token / Tushare 需 token，网络默认关，开启需显式确认）→ 快照列表（合约/日期/标的数/体检）→ 合成示例入口（标 SYNTHETIC）。

### 6.6 设置 Settings
服务连接/Token → 数据与网络（实时行情开关、数据源状态、自检）→ 外观（主题/密度/涨跌色）→ 新手模式开关 → 关于/免责声明。

## 7. 新手模式（Beginner Mode）
- 默认开启，可在设置/顶栏关闭；状态存 localStorage `qc_beginner`。
- 开启时：隐藏高级参数；术语后加 `?` tooltip（白话解释）；每页底部固定"下一步建议"条；
  空态优先给"一键示例"；结果页展示"怎么看这个结果"三句话解读。
- 关闭时：展示全部字段、导出、插件、DSL 等专业入口。

## 8. 实时行情表现规则
- 状态：`实时`（绿点 + 最后更新时间）/ `休市`（灰点 + 最近收盘）/ `离线`（黄点 + 快照日期）。
- 网络未开启时全站不得发起网络请求；显示"实时行情未开启，去设置开启"。
- 实时价格变化用极轻的 flash 动画（≤200ms），尊重 reduced-motion。
- 数据源、延迟、最后更新时间在行情页/状态栏可见。

## 9. 验收（UI 重构）
- `pnpm -C ui test`、`pnpm -C ui build` 通过；Playwright 全部通过（更新选择器）。
- 新首页、行情、回测、数据、设置页在 1440×1000 与 390×844 无横向溢出。
- 每页 loading/empty/error 三态可演示；新手模式开/关可演示。
- 深/浅色 + 色盲模式对比度检查通过；截图更新到 `docs/screenshots/`。
