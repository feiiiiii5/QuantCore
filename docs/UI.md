# UI — 交互与页面

前端 `ui/`：React 19 + Vite + TypeScript；设计令牌在 `ui/src/styles.css`；zh-CN 默认。
构建：`pnpm -C ui build`；开发：`pnpm -C ui dev`（Vite 将 `/api` `/ws` `/health` 代理到 `127.0.0.1:8000`）。
生产：`qc serve` 同源托管 `ui/dist`，无 CORS、无 CDN；Monaco/ECharts 均本地 bundle。

## 导航
行情 / 选股 / 策略 / 回测 / 实验 / 研究 / 模拟 / 数据（+ 设置）；顶部全局搜索（代码/名称/行业，⌘K 聚焦，选中跳转 K 线）；
底部状态栏显示数据截止日、数据源、任务状态、引擎/版本与本地地址。

## 页面

### 行情 `/`
- 全市场/主板/创业板/科创板指数卡 + 迷你走势；涨跌/涨跌停/停牌分布；行业板块涨跌。
- 证券列表（代码/名称/行业/最新/涨跌/换手/交易所/类型/上市日）；证券资料与 PIT 财务公告视图，点击切换 K 线；K 线含 MA5/MA20/成交量/十字线/缩放。
- 数据来源标注 `SYNTHETIC`；无快照时使用 40 只合成回退，页面会提示。

### 选股 `/screener`
- 预设因子（动量/低波动/趋势/流动性/质量动量）、板块、剔除 ST、最小成交额。
- DSL 表达式（`rank/ret/ma/std/ts_mean/...`），运行后在表格展示匹配数/行业/市值/分数；支持浏览器本地保存与 CSV 导出。

### 策略 `/strategy`
- 本地插件：data/strategies/*.py 的发现/静态审计/运行回测（后台任务）；页面明确静态审计不是安全沙箱。
- 七个模板与 JSON Schema 默认参数；Monaco 本地编辑器编辑参数 JSON；调用 `/api/strategies/validate` 显示校验结果。
- “运行回测”把模板/参数带到回测页；编辑器按路由懒加载，首屏不下载 3.3MB Monaco chunk。

### 回测 `/backtest`
- 模板/参数/日期/初始资金/成交模型；高级费用/成交/风险限制（最大持仓数、单票最大权重）；可选基准代码；提交 `/api/backtest` 后台任务，WS 进度，可取消。
- 完成后加载实验：总收益/年化/Sharpe/最大回撤/换手/费用，可选基准收益/超额/信息比率，净值+基准+回撤图，逐笔交易表。
- 点击任一笔交易打开“交易解释”：价格、数量、成交额、佣金/印花税/过户费/其他/合计、触发原因与 trace 摘要。
- HTML 报告与可选 PDF 导出（本地 Chrome/Chromium；无浏览器时 API 返回 503，不伪造文件）。

### 实验 `/experiments`
- 运行记录（策略/时间/收益）；选择后加载净值与指标；支持复现校验、HTML 报告、ZIP 导出。
- 勾选多条实验对比净值曲线（最多 6 条）；`DELETE` 仅在 API 层提供，UI 未暴露删除以避免误操作。

### 模拟 `/paper`
- 本地虚拟账户：创建/选择快照会话、逐日推进/自动推进、重置/删除；市价或限价委托、撤单、持仓/委托/成交/权益曲线、信号 CSV、本地权益阈值提醒；多会话只读组合视图（权重合计=1，归一化聚合）；服务端模拟时钟“持续模拟”（历史快照推进，非实时行情）；明确不连接券商、不产生真实委托。

### 研究 `/research`
- 稳健性：选择实验做 Deflated Sharpe、PBO/CSCV、成本敏感性、Monte Carlo 路径/分位、容量估算；近似口径在页面注明。
- 因子诊断：表达式、预测期、分层数；IC/RankIC 时间序列、分层平均收益、衰减曲线、覆盖率/ICIR、分层明细；多因子相关性矩阵（日截面 Pearson/Spearman 均值）。
- 参数扫描：模板 + JSON 网格或确定性随机抽样（mode/sample_size/seed，服务端上限 200 组合），输出 Sharpe 热力图/表格与最佳点。
- 滚动验证：模板/参数/折数，输出各折收益/Sharpe/回撤/交易数与柱状图。
- 归因：选择实验，按行业展示 FIFO 已实现+未实现盈亏（含费用，近似研究口径）。

### 数据 `/data`
- 数据仓库行数/大小、快照数、实验产物、可用空间；快照列表（证券/交易日/质量/类型）。
- 数据源能力（AKShare/mootdx/Tushare/Local/Synthetic）；“增量更新+构建快照”后台任务与进度。
- “一键示例”调用 onboarding：生成 SYNTHETIC 面板、快照并跑示例回测，跳转实验页。

### 设置 `/settings`
- API 地址（留空同源）/Bearer Token；测试连接；浅/深色、舒适/紧凑、红涨绿跌/绿涨红跌/色盲友好；保存后全局即时生效。

## 状态与错误
- 所有数据页有 loading/empty/error + 重试；API 错误显示 `detail`。
- 空快照/空实验有明确引导；不把异常吞成空白。
- `qc serve --open` 的 `?token=` 会被入口保存到 localStorage 并从 URL 移除，避免出现在 Referer/历史记录。

## 预算与验证
- 初始 JS 约 1.4MB raw（ECharts 1.0MB + app 0.31MB + React 0.05MB）；Monaco 3.3MB 仅 `/strategy` 按需加载。
- Playwright 预算测试：首屏 <5s、初始 JS <2MB raw、无 console/page error；移动端 390px 无横向溢出。
- `make e2e`：构建 UI + 隔离 `qc serve` + 18 条 Playwright，覆盖行情/选股/回测/实验/数据/策略/设置/研究/稳健性/模拟/onboarding/暗色/性能/移动端。

## 兼容性
- 桌面优先（macOS/Windows），移动端为响应式兜底：≤900px 侧栏折叠为图标，表格横向滚动。
- 浏览器：Chrome/Edge/Safari 当前版本；Playwright 使用本机 Chrome channel。
