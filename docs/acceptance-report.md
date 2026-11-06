# 验收报告 — 对照任务书

> 状态：2026-11-02（Apple 设计语言 + 成熟开源方案重构轮 R4）。M0–M10 功能门禁完成；R2（qc doctor/demo、部分成交、本地工具链）与 R3（产品理念、UI 重构、实时行情、真实数据、零基础引导）保持全绿；R4 按 Apple HIG 重做前端设计系统（Radix UI / framer-motion / sonner / cmdk / vaul / lightweight-charts），以 exchange-calendars 真实 XSHG 日历替换启发式，修复实时行情与 provider 的一组正确性问题，并端到端验证真实联网行情（REST + WebSocket）。授权 vendor 行情、签名/公证安装包仍是文档化限制。
> 本报告只写实际运行过的命令与结果。`docs/features.json` 为逐项真相源（M0–M10 **134/134**，R5 增量 **6/6**，R6 增量 **4/4**，R7 增量 **5/5**，R8 增量 **7/7**）。

> **交接记录（2026-11-02）**：上一会话留下的迁移交接文档（377 行）的独有内容已吸收进
> `docs/PROGRESS.md`（开发环境/门禁基线/提交流程/工作边界）与 `README.md` 文档索引，交接文件已删除；
> `docs/ARCHITECTURE.md` 与 `docs/RELEASE.md` 中与当前代码事实不符的历史表述（导航数量、子进程资源限制、
> Playwright 数量、Windows 验证状态）已修正。下列已知限制保持原文，未做弱化。

## 2026-11-06 实时工作流、策略实测与 Sites（R8 / Q-005）

- 本地最终检查：Python **579 passed / 2 skipped**（45.46s）；UI **39 passed / 18 files**；真实服务浏览器 **20/20**（26.8s）；Ruff 检查与格式 **197 文件**、mypy **114 文件**及 TypeScript/Vite 构建通过。C++ 源码本轮未改，上一轮 ctest **101/101**；本轮原生扩展 0.1.1 的既有验证脚本与差分 **6/6** 再次通过。
- 行情与 K 线：逐证券源时间/陈旧状态、Eastmoney→Sina 缺项回退、独立日线接口及直接代码查看、当前蜡烛更新。真实公开源仅实测 600000 的闭市报价和 60 根日线；不将闭市样本说成盘中时延验证。
- 模拟交易：新增实时模式，按有效源时间和下单后新增成交量撮合；首帧/换源/过长缺口重建基线。修复涨跌停缺失时错误成交、累计量回拨与跨源切回重启后重复使用成交量；对应回归在修复前失败。真实服务 E2E 验证创建账户、下单、离线等待；盘中真实报价成交尚未在浏览器验证。账户不处理公司行为或盘口排队，无真实下单。
- 性能：相同输入与五次采样，面板导出 **290.19→82.80ms**，字节相同；三候选信号相对原 pivot 算法 **3.83–5.89×**，权重相同。原生入口 **1.73ms** 与暖 Snapshot 包装 **9.65ms** 分开记录，不混作端到端；方法、采样及未测规模见 [性能记录](PERFORMANCE.md)。原选股回归的计数位置随字段物化入口更新，保留实际 API 结果与每字段一次的约束，未放宽断言。
- 策略与数据：实现三候选并以固定协议完成八只存续股 **5120 条日线、34 条近似现金事件**的小样本开发/留出与成本压力研究，**24/24** 实验通过通用重放。保留反转策略亏损结果；样本选择、未知到账日、非 PIT 与近似事件限制见 [策略实测](STRATEGY-STUDY.md)。加性 qfq 差价漂移不再制造假分红，在线/离线共用因果因子重建，原始 OHLCV 未为质量门删改。
- Sites：发布同一私有前端，C++/Python/数据/账户保留本机；精确 HTTPS 来源允许 CORS/PNA，Bearer、Host/Origin 和 WS 校验保持有效。设置只在健康及受保护元数据均成功时报告连接；保存另一服务后清旧查询和共享 WS，旧帧不能污染新连接。真实已登录浏览器的 Sites→loopback/PNA/WS 完整链路未验证，原因与操作见 [Sites 说明](SITES.md)。
- 评审整理：依照 [行情测试拆分意见](https://github.com/feiiiiii5/QuantCore/pull/2#discussion_r4493729430) 将五项新鲜度回归及共享录制 fixture 拆成独立模块，三个文件分别 457/72/52 行；两模块 32 passed，运行逻辑不变。
- 当前界面证据：[行情](screenshots/market.png)、[实时模拟离线等待](screenshots/live-paper.png)、[成本情景](screenshots/cost-sensitivity.png)，均为实际界面和明确标注的合成演示数据。未重新验证全市场、真实 Tushare Token、授权 L2、签名安装包或实盘。

## 2026-11-06 全仓正确性与性能收敛（R7）

本轮以 `406b687` 为基线，继续使用 C++20 原生生产回测，仅本地验收，无部署。三名 worker 分别检查原生账本、数据与界面流程，并交叉复核修复后的行为；历史外部数据与平台证据仍保留原日期。

- 公司行为：面板/快照的现金分红与送转按原生证券顺序接入回测及批量回测。除权日停牌或连续缺价时同步调整估值基准；卖出及退市强平指标使用账本实际 FIFO 盈亏。明确记录税前、除权日现金到账口径；配股认购与请求但未实现的分红税不再被静默忽略。旧实验缺失新字段时保留旧口径，避免 replay 暗中改变条件。
- 基准：按同一有效公司行为计算无成本、无税、分红现金不复投的买入持有曲线；日收益只比较相邻有效报价，缺少窗口首尾时超额收益为空。已复核现金保留、连续缺价事件、首笔买入前事件与边界缺价。
- 数据：替换仓库前完成抓取与质量检查；失败不提前清仓。增量更新核对 provider、证券范围与配置身份；跨 CLI/API 状态文件共享仓库来源与 SYNTHETIC 标记，空财务/公司行为表真正清除旧内容。Tushare CLI/worker 补齐网络授权与代码参数，月末增量使用实际下一日。
- 性能与流程：快照缓存保留文件变更检查；选股复用字段矩阵，不为每个命中证券重复构建全历史。行情、首页自选、命令面板可查首 1000 条以外的证券；导入自动快照等待正确任务，参数修改清除旧校验结论。真实浏览器核对替换导入、自动快照、证券搜索、回测与移动布局。
- 最终本地全套：Python **463 passed / 2 skipped**（38.58s），C++ **101/101**，Vitest **29 passed / 15 files**，真实服务 Playwright **19/19**；Ruff lint/format **175 文件**、mypy **109 源文件**、TypeScript/Vite 构建通过。Python 仅有既有 Starlette/httpx 弃用提示；两项跳过不计为通过。
- 原生扩展 **0.1.1** 重新构建，C++/参考差分 **6/6** 与既有 `scripts/verify_cpp.py` 通过。相同合成输入的选股 API 五次采样中位数 **627.68ms → 36.37ms**（约 17.26 倍），响应逐项一致；原生小集测量与方法见 [PERFORMANCE.md](PERFORMANCE.md)。

首次云端检查：macOS、UI、Windows smoke 与未签名客户端打包通过；Ubuntu 在安装构建依赖时连接清华镜像超时，未进入编译/测试。云端安装改用官方 PyPI、`--frozen` 锁文件及后续 `--no-sync`，新提交结果以实际 CI 为准，不将首次 Ubuntu 失败计为通过。

`3244c56` 的五项云端检查通过后，自动评审指出两处边界，均已实际复现并修复：有限旧收盘价在送转除权日及下一停牌日覆盖调整估值（样本净值 15000 而应为 10000）；Tushare fixture 的后缀代码日线为空、财务/公司行为表按不存在的 `code` 列筛选失败。停牌估值与复牌回归修前 1 failed/1 passed；Tushare 三种代码形式与真实离线 CLI 文件导入回归修前 7 failed。修复后重新构建扩展并运行上述最终全套，浏览器 19/19 再次通过（27.6s）。

后续评审继续发现基准未排除停牌旧价的同类问题：现已将停牌报价视为缺失，公司行为仍在缺价期间推进。新增停牌结束、复牌、首次可交易前不领权益及现金不复投回归，修前 3 failed/1 passed，修后相邻组 33 passed；最终 Python 全套 463 passed/2 skipped。C++ 与前端代码未因这项基准修正改变，浏览器证据沿用上一完整流程。

未重新验证真实 Tushare Token、全市场历史导入、5500×20 年/10000 组规模门禁或生产部署。模拟账户仍有独立 Python 撮合与公司行为限制；本轮回测修复不表示模拟账户获得相同能力。

## 2026-11-06 产品文档与首次运行验收

中英文 README 围绕策略验证、实验比较、研究条件和后续分析重新组织，并以真实实验对比及成本情景截图说明功能。能力与平台表述已按源码复核：信号为 CSV 导出，固定参数分段回测不宣称自动训练调参，实验分析与独立配置的研究任务分别说明。

在新建专用工作目录中，实际执行 README 的最小运行依赖安装（`uv sync --frozen --python 3.12 --default-index https://pypi.org/simple`）、前端 frozen 安装/构建、`qc demo --data-root data` 与同目录 `qc serve`，全部成功。原生后端为 `cpp`，服务可读取演示的快照和实验，UI 可访问；测试服务与工作目录已清理。未改依赖锁文件或运行代码。

快速上手同步修正了演示/服务数据目录不一致、前端依赖缺失、CLI 回测必须显式指定快照，以及 Windows/Tushare 路径的范围说明。文档中的相对链接与图片均核对到实际文件。未部署应用。

## 2026-11-06 本地增量验收：稳健性研究口径（R6）

本阶段仅本地构建、测试与验收，不部署上线。本轮没有推送新提交，也没有修改运行时依赖或 C++ 引擎；真实回测和成本重跑继续经过 C++20 `qcore`。

- PBO：按[原论文算法 2.3(f,g)](https://carmamaths.org/jon/backtest2.pdf)修正 relative-rank/logit 方向。公开 OOS 排名仍为 1 最好；内部并列采用平均秩，保留本项目 `logit <= 0` 计入 PBO 的政策。相同收益不是独立稳健证据，不再产生正 logit。持久化与 HTTP 回归共 **3 passed**；原方向的两个用例实际失败，并列补充用例也在修复前失败。
- 因子分组：稳定零起排名分桶，修复 5 只证券分 5 组时底组空、顶组重复的偏移；并列按证券原顺序，非有限值不分组。新增 **6 passed**，其中原实现 **3 failed / 3 passed**；真实 `analyze_factor` 报告逐组收益与已知前瞻收益一致。
- Monte Carlo：回撤峰值纳入初始资金 1.0。持久化 -1% 日收益、单日采样时，原实现的回撤分位数全为 0，修复后为 1%；新增 **1 passed**。采样模型未改变。
- 成本敏感性：费用倍数改为情景条形图与指标表，保留 0、0.5、任意小数及单点，费用从 1e-4 元转换为元。真实浏览器从实验进入研究，核对响应 `run_id`、真实 C++ 后端与每行的收益/年化/Sharpe/回撤/费用；默认、小数、单点情景均通过。原界面使用时间坐标，不能正确逐项展示这些情景；新增浏览器断言在原界面失败。
- 本地全套：Python **383 passed / 2 skipped**；Vitest **20 passed**；真实服务 Playwright **19/19**，新增成本流程的桌面 1440×1000 与手机 390×844 检查无页面横向溢出、无控制台错误。TypeScript/Vite 构建通过；Ruff lint/format（164 文件）与 mypy（106 源文件）通过。
- C++：本地编译扩展与 `engine_backend=cpp` 已核对，既有 `scripts/verify_cpp.py` 通过，差分 **6/6**。300×965 合成面板的 20 因子约 20.94ms，单引擎约 2.78ms；仅为本机合成基准，不构成全市场结论。

界面证据：[桌面成本情景](screenshots/cost-sensitivity.png)、[手机成本情景](screenshots/cost-sensitivity-mobile.png)，均为本地 SYNTHETIC 数据。未进行部署、实盘、授权数据源或其他平台验收；旧 CI 结果只适用于旧提交。

## 2026-11-06 增量验收：研究证据与账户正确性

新增内容围绕真实流程：实验归一化比较与条件差异、原实验数据/参数复用与父记录、稳健性跳转，以及账户和行情身份正确性。没有增加运行时依赖或真实下单能力。旧 M0–M10 证据保留原核对日期，不能理解为本次重新验证了所有外部数据和发布平台。

- Python 全套：`uv run --no-sync pytest -o addopts=--strict-markers` → **373 passed / 2 skipped**。
- `ruff check` / `ruff format --check`、mypy（106 源文件）通过。
- 前端：`NODE_OPTIONS=--no-experimental-webstorage pnpm -C ui test` → **19 passed**；TypeScript 与生产构建通过。
- 真实服务浏览器：既有 E2E **18/18**，覆盖主流程、插件、模拟账户、深色与移动端。新增流程用独立真实服务与 Playwright CLI 验证了 URL 选择、归一化/资金差异提示、来源数据与参数复用、新实验父记录、稳健性上下文；桌面 1440×1000 与手机 390×844 均无页面横向溢出，控制台 0 错误。首页实测未请求 Monaco。
- C++：`uv run --no-sync python scripts/verify_cpp.py` 通过，差分 **6/6**。300×965 合成面板，引擎约 **2.79ms**，20 因子约 **24ms**；并非全市场或实盘结果。
- 原实现红测：跨起始日 50/50 组合错误显示 +3.3333%，持仓重开损失 20 元成本；证券切换保留旧报价、WS 停帧不再刷新、账户切换被迟到响应覆盖。对应回归均已通过。
- 本机 Node 26 的原生 Web Storage 与现有 jsdom 环境冲突，因此测试显式关闭该 Node 实验能力；未更换锁定依赖。

CI 安装补充：初次 PR CI 的 Ubuntu 在读取清华镜像的锁定 `httptools==0.9.0` Linux wheel 时返回 HTTP 403（[失败日志](https://github.com/feiiiiii5/QuantCore/actions/runs/42168507236/job/127730548537)）。PyPI 官方文件源上的同一文件已实际下载并核对 SHA-256，与原锁完全一致。锁内安装包 URL 统一改为官方文件源；索引、版本、依赖关系和哈希均未变化，不修改 workflow。 独立 TOML 审核确认仅 1540 个安装包地址发生前缀替换；镜像索引下的离线 locked dry-run 与 Linux 目标 dry-run 通过。本机使用官方构建索引的全新 frozen 安装通过，锁字节未漂移。

数据往返补充：小型合成面板的空公司行为表在原实现保存后被省略，重开从 `(0,10)` 变为 `(0,0)`，数据指纹因此改变。两条保存路径现保留空表结构；两个写入端的结构检查及连续来源派生在修复前均失败、修复后通过。旧文件已经丢失的空表结构不做猜测恢复。

自动评审补充：来源回测页经侧栏返回普通回测时，原实现仍提交旧 `source_run_id`，真实浏览器检查已复现。修复在退出来源模式时清除来源选择与恢复标记，同时保留普通快照选择。修复后真实服务往返检查通过：普通回测不再携带父记录，返回同一来源后恢复原数据指纹与父记录；控制台 0 错误。

验证取舍：本次没有修改 C++ 核心，不重新建立另一套撮合实现或重跑全市场规模试验；检查集中于收益、账本、数据身份、任务生命周期及真实界面。真实 Tushare Token、授权实时源、Windows 安装、签名包和实盘能力仍未验证。

本次界面证据：[桌面对比](screenshots/research-comparison.png)、[手机对比](screenshots/research-comparison-mobile.png)，均为明确标注的 SYNTHETIC 数据。

## 里程碑
| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 底座 | ✅ | `make setup`、wheel 构建、`engine_backend=cpp`；CI macOS/Ubuntu 全量 + Windows pure-Python smoke |
| M1 C++ 基础 | ✅ | ctest 95/95；roll/cross 内核（含 neutralize）/指标/线程/面板/差分 |
| M2 数据中心 | ✅ 基本 | Synthetic/LocalFile/Tushare fixture+live code path/AKShare/mootdx + **Sina 公开真实数据源**（未 Token，全 universe/日线/近似复权）；Parquet+DuckDB+SQLite；快照/质量/PIT 财务；数据体检 API/CLI；真实 3 只样本 import→snapshot→integrity=ok→回测已跑通；Tushare 真实 Token 未验证 |
| M3 回测引擎 | ✅ | ctest 95/95；C++/参考差分 6/6；规则/费用/T+1/手数/涨跌停/停牌/trace/指标/风险限制/基准比较 |
| M4 SDK/CLI/策略 | ✅ 大部分 | DSL/模板/实验/HTML+可选 PDF/子进程 sandbox worker/C++ parallel sweep/CLI/replay |
| M5 服务层 | ✅ | FastAPI 契约、Bearer/Host/Origin/no-CORS、SQLite 任务队列、WebSocket、取消/崩溃恢复、GZip、本地通知；R3 增 live 行情 REST/WS、数据体检、onboarding/presets/watchlist API；R4 真实 XSHG 交易日历、live/provider 正确性修复、UI 共享 WS 消费 |
| M6 UI V1 | ✅ | R4：Apple 设计语言 v2（毛玻璃/34px 标题/8pt 网格/克制动效），Radix+framer-motion+sonner+cmdk+vaul+lightweight-charts 成熟栈，10 页重写，echarts 移除（初始 JS 1.09 MB→0.60 MB）；Playwright **18** 条；ui-audit 10 路由 0 console/0 溢出 |
| M7 研究工具 | ✅ | IC/RankIC/ICIR、分层、衰减、因子相关、grid/random 扫描、滚动、归因、DSR/PBO、成本敏感性、Monte Carlo、容量 |
| M8 V2 数据 | ✅ 大部分 | 证券资料/PIT/ETF+可转债/合成分钟线/V2 数据集目录已做；C++ 回测仍按 board 手数，分钟线为 SYNTHETIC |
| M9 V3 模拟交易 | ✅ | 虚拟账户/逐日回放/委托撤单/成交（含按成交量参与率的部分成交）/信号 CSV/提醒/本地插件/只读多策略组合/服务端模拟时钟自动推进；R3 提供可选实时行情（公开网页源，展示用、无真实下单）；无授权 vendor 实时 feed |
| M10 发布 | 🟡 大部分 | wheel/UI/文档/许可/SBOM/audit/release/perf gate + Electron dev shell + unsigned macOS zip + Windows zip（windows-latest CI 构建）；无签名/公证、未做安装运行验证 |

## 成熟方案重构轮门禁（R4）
```bash
make lint
# ruff check/format 通过；mypy 105 files 无问题

uv run pytest
# 354 collected；352 passed / 2 skipped

ctest --test-dir build/cmake --output-on-failure
# 95/95 passed

pnpm -C ui test
# 10 passed (5 files)

pnpm -C ui build
# 通过；initial index 595 kB raw / 176 kB gzip，charts/motion/overlays 分包，Monaco 懒加载

make e2e
# 构建 UI + 隔离 qc serve + Playwright 18 passed（Apple 风格新 UI）

node ui/scripts/ui-audit.mjs   # QC_BASE=:8150 已 seed 演示服务
# 10 路由 + 移动端 + 深色：全部 200、0 console error、0 横向溢出、0 个无可访问名称控件

# 真实联网行情（服务端显式开启网络）
QC_ALLOW_NETWORK=1 uv run qc serve --port 8151 --ui-dir ui/dist
# GET /api/live/status → {"enabled":true,"state":"live","source":"sina","latency_ms":~205,"market":{"phase":"lunch",...}}
# WS /ws/live?codes=600000,000001 → 收到 snapshot 帧：浦发银行 10.14 (+1.20%)、平安银行 11.58 (-0.52%)、4 个指数
# 浏览器实测：AppBar 指数与行情页读数随 WS 更新（3,635.67 → 3,635.66），0 console error
```

## R4 增量（Apple 设计语言 + 成熟方案）

- **设计系统 v2**：`docs/DESIGN-SPEC.md` 重写为 Apple HIG 落地规范（Clarity/Deference/Depth、系统字体栈、34px 标题阶梯、8pt 网格、毛玻璃材质、hairline、120–260ms purposeful 动效、reduced-motion、对比度）；`ui/src/styles/**` 全部重写（tokens/base/layout/components/business/overlays/views，删除 legacy 兼容层），16 个新原语（Button/Field/Input/Textarea/Select/Switch/PageHeader/Callout/List/ListRow/ProgressBar/Dialog/Sheet/Menu/Tooltip/Popover/Toaster）。
- **成熟开源方案**：@radix-ui/react-*（无障碍原语）、framer-motion（页面转场/弹层）、sonner（通知）、cmdk（⌘K 面板）、vaul（移动 bottom sheet）、lightweight-charts（统一图表，移除 echarts：初始 JS 1.09 MB → 0.60 MB）、TanStack Table/Virtual/Query、lucide-react。
- **页面**：10 页按 Apple 风格重写（今日/行情/回测/数据/模拟/研究/选股/策略/实验/设置）；结论先行、分组列表、KPI tile、三态、新手模式、移动端 tabbar + vaul「更多」；无横向溢出、0 console error。
- **真实交易日历**：`trading_calendar.py` 封装 exchange-calendars XSHG（交易所节假日/周末/会话），替换 `realtime/clock.py` 的星期几启发式；2024 春节/国庆、跨节假日 next_open、节后首日 last_trade_date 均有离线测试。
- **实时行情正确性修复**：920xxx 北交所映射、盘前误标停牌、非自选股报价不刷新、异常路径 UnboundLocalError、闭市轮询 3s→15s、东财 turnover 被清零、qfq/raw 重复日期、Sina 历史窗口时区、provider 并发上限与 quota 一致；新增 provider→quality 集成回归。
- **UI 实时链路**：`lib/liveStream.ts` 共享 WebSocket（每个代码集一个连接、退避重连、写入 react-query 缓存），失败回退 15s HTTP 轮询；已用真实网络 + WS 帧验证。
- **前端工程**：Vite dev 代理重写 Origin（修复 dev 模式 403）、manualChunks 拆包、`ui/scripts/ui-audit.mjs`（截图 + overflow/console/a11y 审计）、tsc/vitest/build 全绿。

## 重构轮门禁（R3）
```bash
make lint
# ruff check/format 通过；mypy 104 files 无问题

uv run pytest
# 321 collected；319 passed / 2 skipped

pnpm -C ui test
# 10 passed (5 files)；pnpm -C ui build 通过

make e2e   # 本机 Chrome；隔离 qc serve + 新 UI
# Playwright 19 passed（新路由 /today、真实回测任务、数据体检、命令面板、移动端等）

make verify-cpp
# ok：C++ backend、差分 6/6、性能门禁

# 真实数据链路（Sina 公开接口，QC_ALLOW_NETWORK=1，样本 3 只）
uv run qc data update --provider sina --codes 600000,000001,300750 --start 2024-01-01 --end 2026-10-31 --data-root /tmp/qc-real-v2/data
# quality_passed=true；2049 rows；0 warnings；0 quarantined
uv run qc snapshot build --data-root /tmp/qc-real-v2/data --snapshots-root /tmp/qc-real-v2/data/snapshots
# snapshot=snap_dd1cff47d13ae1e3；source=SINA；synthetic=false；qpanel=true
uv run qc data integrity --snapshots-root /tmp/qc-real-v2/data/snapshots
# status=ok；coverage=100.00%；accuracy={ohlc:0, volume_amount:0, limit:0, adjustment_breaks:0}
uv run qc backtest run --template dual_ma --snapshot <snap> --snapshots-root ... --start 2024-06-01 --end 2026-10-31
# engine_backend=cpp；snapshot source=SINA synthetic=false；总收益 83.54%、年化 28.82%、Sharpe 1.05、最大回撤 31.90%、55 笔交易（研究示例，不构成投资建议）
```

## 重构轮增量（R3）

- **产品理念与设计规范**：新增 `docs/PRODUCT.md`（市场观察、三条支柱：看得懂/跑得通/信得过、研究卡片/数据体检/行情→研究直连）与 `docs/DESIGN-SPEC.md`（IA、tokens、组件契约、逐页规格、新手模式、实时行情表现规则）。
- **UI 全面重构**：新增 `/today` 驾驶舱（市场状态带、自选、新手进度、最近研究、数据体检）与 `/market` 实时优先行情页；AppBar 实时指数条 + ⌘K 命令面板 + 新手模式开关；token 化设计系统（浅/深色、密度、红绿/绿红/色盲三套涨跌色）；17 个通用组件；8 个页面按「结论先行 + 三态 + 新手提示」重做。截图见 `docs/screenshots/`。
- **实时行情（可选联网）**：`GET /api/live/{status,indices,quotes}` + `WS /ws/live`；上海市场时钟、Eastmoney→Sina 双源与降级、限速缓存、离线/休市/异常显式状态；默认完全离线（`QC_ALLOW_NETWORK=1` 才联网），测试不联网（fixtures）。
- **真实数据与准确性**：新增 Sina 公开行情 provider（全 A 股 universe 5576 只、原始日线约 2000 根、volume 单位为股已实测；腾讯 qfq 推导复权/近似公司行为，并对 vendor 因子跳点做「持续性 + 涨跌停合理性」过滤）；新增数据体检（覆盖率/缺口/OHLC/量额/涨跌停/复权连续性/跨源抽样，默认离线）；`GET /api/data/integrity` + `qc data integrity`；质量门禁对少量坏行改为隔离并告警（不整批失败）。真实 3 只样本链路见上，integrity=ok 且 accuracy 全 0。
- **零基础引导**：`/api/onboarding` 4 步（data/backtest/result/data_health，自动检测 + 幂等完成）、6 个白话策略预设、`/api/watchlist`、首页新手清单 + 设置页新手模式；新增 `docs/TUTORIAL.md`（163 行零基础教程）。
- **测试**：pytest 321 collected / 319 passed / 2 skipped（R3 新增 live 11、sina 26、integrity 11、onboarding 16 等及 provider 回归测试）；Playwright 19/19（新 UI 重写选择器）；UI vitest 10。

## 交接后增量轮门禁（R2，历史记录）
```bash
make lint
# ruff check/format 通过；mypy 91 files 无问题

uv run pytest
# 240 collected；238 passed / 2 skipped

pnpm -C ui test
# 10 passed (5 files)

pnpm -C ui build
# 通过（tsc + vite；仅有既有 chunk-size 提示）

make e2e   # 需要本机 Chrome；会构建 UI、启动隔离 qc serve
# Playwright 18 passed（含设置页自检、模拟交易部分成交后的状态断言）

make verify-cpp
# ok：C++ backend、差分 6/6、open 0.22ms、20 factors 20.7ms、engine 2.8ms、ratio 165x

make doctor
# summary ok（pass=13 warn=0 fail=0 skip=1）engine=cpp

make demo
# engine_backend=cpp；snapshot/run/HTML 报告生成；1208 交易日；SYNTHETIC

make bench-scale
# 默认 800 证券：总墙钟 4.51s、峰值 RSS 1583 MiB、qpanel open 0.3ms（详见 docs/PERFORMANCE.md）
```

## 本轮增量（交接后）

- **交接完成**：迁移交接文档的独有内容已并入 `docs/PROGRESS.md`/`README.md`，交接文件已删除；`ARCHITECTURE`/`RELEASE` 漂移已修正（见上方交接记录）。
- **本地自检**：`qc doctor` / `GET /api/doctor` / 设置页「本地自检」卡片——只读离线检查 Python/.venv、C++ 引擎、数据仓库、快照、UI 构建、Node/pnpm、端口、磁盘、Git、Chrome、C++ 测试二进制；输出 pass/warn/fail/skip 与修复提示；`--strict` 可作脚本门禁。
- **一键演示**：`qc demo` / `make demo`——SYNTHETIC 面板 → Parquet → 不可变快照 → C++ 回测 → HTML 报告，默认写入 `data/demo/` 与 `experiments/<run_id>/`（均 gitignore），约 2–3s。
- **本地测试工具链**：`make doctor/demo/test-quick/verify-local/bench-scale`、`scripts/local_verify.sh`（分段耗时 + PASS/FAIL）、`scripts/scale_bench.py`（面板/Parquet/.qpanel/engine/峰值 RSS）、`docs/LOCAL-TESTING.md`（命令矩阵 + 隔离方式 + 故障排查）。
- **模拟交易部分成交**：按日成交量参与率上限（默认 10%）分笔成交，新增 `partial` 状态、跨交易日续成、逐笔费用/持仓/T+1 正确；旧 session JSON 向后兼容；语义见 `docs/paper-trading.md`。
- **测试**：pytest 240 collected / 238 passed / 2 skipped（新增 44 条：doctor 20、demo 9、api doctor 4、paper partial 10、paper api 1）；Playwright 18/18（修正订单状态中文映射后的断言）；UI vitest 10。

## 硬性约束自查
- [x] C++20 核心路径：panel/kernels/engine/metrics/expr；生产回测走 `_qcore.Engine`。
- [x] 本地优先/运行期零 CDN：数据、策略、Monaco、lightweight-charts 均本地打包；UI 无远程字体/资源。
- [x] 同源部署：`qc serve` 同时提供 `/api` 与 `ui/dist`；Vite dev 使用 `/api` `/ws` `/health` 代理到 8000。
- [x] 仅研究与模拟：无真实下单；`BrokerGateway` 未实现；界面与报告有“不构成投资建议”。
- [x] 认证：Bearer token、Host/Origin 校验、默认无 CORS、可显式允许准确 HTTPS 来源、loopback only；token 从 `qc serve --open` URL 持久化后立即从地址栏移除。
- [x] 合成数据标 `SYNTHETIC`；真实 A 股数据可经 Sina 公开接口导入（`QC_ALLOW_NETWORK=1`，非商用、不得再分发），Tushare 真实网络需 Token，未验证。
- [x] features.json 全 true：**134/134**（R4 新增 6 项：XSHG 真实日历、provider/live 正确性修复、Apple 设计系统 v2、统一 lightweight-charts、UI 共享 WebSocket、前端工程/dev proxy/audit harness）。
- [x] 网络默认关闭：实时行情与真实数据导入均需显式 `QC_ALLOW_NETWORK=1`；测试只走录制 fixtures，不联网。
- [x] 真实数据准确性实测（2026-11-02）：Sina 3 只样本 2049 根日线，质量门禁 passed、0 告警、0 隔离行；`qc data integrity` status=ok、coverage=100%、accuracy 全 0；真实快照上 C++ 回测成功（synthetic=false/source=SINA）。
- [x] 实时行情：REST/WS、双源降级、真实 XSHG 日历、离线/休市/异常显式状态；UI 通过共享 WebSocket 消费并回退轮询；用于展示与本地虚拟账户，不参与真实下单。
- [x] 真实联网验证（2026-11-02）：QC_ALLOW_NETWORK=1 下 /api/live/status=live、source=sina、WS 帧含真实个股与 4 指数，浏览器读数实时更新且 0 console error。
- [x] M8 分钟线（SYNTHETIC）/V2 dataset catalog、M9 模拟时钟连续模拟已完成（限制见下）。
- [ ] 真实 Tushare 数据跑通：无 Token，未验证（Sina 公开接口已跑通，作为替代真实源）。
- [ ] 全市场 5500×20y / 10000 组 sweep：未测；默认规模（800 证券 × 1208 天）的耗时与峰值 RSS 已由 `make bench-scale` 实测（见 `docs/PERFORMANCE.md`），不外推为全市场结论。

## 已知缺口（按优先级）
1. **行情/交易限制**：实时行情来自公开网页接口（Sina/Eastmoney，未授权、无 SLA，约 3 秒轮询、无 L2/盘口），用于展示和本地虚拟账户；历史模拟按日成交量、实时模拟按新增成交量参与率近似（无排队/滑点），公司行为（分红送转对持仓的调整）仍未实现；不得声称可实盘。
2. **真实数据限制**：Sina 公开接口非官方、约 2000 根日线（约 2018 年起）；无真实成交额（按 OHLC×volume 估算，已标注）；复权/公司行为由腾讯 qfq 近似推导（`SINA_APPROX`，已过滤 vendor 跳点，但仍是近似）；全市场导入（5576 只）实测约 30–45 分钟，本轮只端到端验证了 3 只样本；Eastmoney 端点在本机网络被限流；Tushare 真实 Token 未验证。
3. **M8 限制**：分钟线为 SYNTHETIC 视图；C++ 回测仍按 board 手数（ETF/可转债 paper 手数已实现）。
4. **M7 口径**：归因仍为行业 FIFO 近似；DSR/PBO/成本/MC/容量为研究近似。
5. **M10 发布**：Electron dev shell、unsigned macOS/Windows zip 已完成；签名/公证、安装运行验证未做；SBOM/audit/perf gate 已完成。
6. **性能验证**：全市场 5500×20y 基准与 10k sweep 未测；默认规模（800×1208）已实测（`make bench-scale`），不构成全市场结论。
7. **规则 TODO(verify)**：ST 各板块幅度、盘后固定价历史范围、新股/退市整理期、分红个税、部分费率。
8. **日历/增量口径（docs/AUDIT-R3.md）**：exchange-calendars XSHG 当前数据到 2026-12-31，之后只能回退星期几判断（已在 live status 记日志，不会 500）；增量 ingest 不会在新除权后重算历史 adj_factor（建议分红季做一次全量重建，或后续实现因子重算）；qfq 跳点过滤在窗口末端/大比例送转/创业板 20% 判板处有已知边界；ST 历史涨跌停不可得，按当前名称与规则表近似。

## 下一步
1. 做 macOS/Windows 签名、公证与安装运行验证；若要商用实时行情，接入授权 vendor feed（替换公开网页源）。
2. 全市场真实数据端到端验证（5576 只 × 20y）：导入→体检→快照→回测，并把覆盖率/耗时回填 `docs/PERFORMANCE.md`；`uv run python scripts/scale_bench.py --n-sec 5500` 已可用（需 ≥16 GiB 空闲内存）。
3. 真实数据准确性继续加固：成交额获取（替代估算）、公司行为与除权参考价核验、更多样本与跨源抽样（需网络时开启）；实现增量 ingest 的 adj_factor 重算提示/自动全量重建；定期升级 exchange-calendars 以覆盖未来年份。
4. 保持无真实下单与本地优先；每轮 make ci-local/e2e/verify-cpp 后再 push；features.json 全 true，“授权实时 feed/签名安装包”作为文档化限制。
5. Windows 包已在 CI 构建但未做安装运行验证。
