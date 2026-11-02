# AUDIT-R3 — 后端复查 + 真实交易日历（2026-11-02）

> 范围：realtime/live（REST + WS）、providers（Sina/Eastmoney/共享复权）、数据质量边界、
> API 与 ui/src/api/types.ts 契约抽样。研究与模拟工作台，不含真实下单；测试全部离线。

## 1. 结论

- 实时时钟已从「星期几 + 手工 holidays」启发式切换为 exchange-calendars 的 XSHG 真实交易日历
  （见 quantcore/trading_calendar.py，Lead 所有）：春节/国庆/周末休市、跨节假日 next_open、
  按到秒的开收盘/午休边界、last_trade_date 均使用真实 session；holidays 参数保留为叠加闭市。
- 后端复查共修复 7 类问题（实时报价映射、盘前误标停牌、缓存永不刷新、服务循环异常路径、
  复权因子推导的换手率/重复行、提供商并发与历史窗口时区），并补了对应离线回归测试。
- API 抽样未见「types.ts 必需字段缺失」；存在若干 TS 未声明的冗余字段与一处未消费的 WS（见 §4）。
- 验收命令全绿：4 个指定测试文件 88 条 + 全量 quick 套件；ruff/format/mypy 通过。

## 2. 修复清单（含回归测试）

### 2.1 python/quantcore/realtime/clock.py

| 问题 | 修复 | 测试 |
|---|---|---|
| 交易日 = 周一至周五（节假日误判为交易日） | 改用 trading_calendar.is_trading_day / next_trading_day / previous_trading_day（XSHG） | test_live_quotes::test_spring_festival_* / test_national_day_holiday_window / test_preopen_after_holiday_reports_last_real_session |
| next_open 只跳周末，跨节假日错误 | 真实 session 递推；午休→当日 13:00，上午盘→当日 13:00，下午盘/收盘后→下一 session 09:30 | test_next_open_handles_morning_lunch_and_afternoon |
| last_trade_date 用 weekday 推算，节后首日盘前会给出错误日期 | 用真实 session：收盘后返回当日，否则返回严格前一个 session | test_preopen_after_holiday_reports_last_real_session / test_weekend_next_open_and_last_trade_date |
| 阶段边界未覆盖到秒 | 保留 09:15/09:30/11:30/13:00/15:00 常量并逐秒断言 | test_session_phase_boundaries_to_the_second |
| 日历数据越界/依赖缺失会让状态接口 500 | 仅在越界时 weekday 兜底（有注释与审计记录），正常路径无启发式 | test_out_of_bounds_calendar_falls_back_without_crashing |

### 2.2 python/quantcore/realtime/quotes.py

- **北交所 920xxx 映射错误**：原 _market_id 把 9 开头一律当沪市，sina_symbol 把 920xxx 映射为 sh920xxx。
  修复为先判 4/8/92 前缀（北交所，market=0 / bj 前缀），再判 6/9（沪市）。
  回归：test_live_quotes::test_new_beijing_920_codes_use_beijing_market。
- **盘前无成交价被误标停牌**：盘前/休市时 f2 为「-」时原逻辑一律 suspended=True，UI 会把全市场标成停牌。
  修复为按市场相位区分：open/lunch 缺价才视为停牌，盘前/收盘后展示昨收且 suspended=False。
  回归：test_preopen_missing_price_is_not_reported_as_suspended。

### 2.3 python/quantcore/realtime/service.py

- **循环异常路径**：_run 中 phase 在 try 内赋值，异常先于赋值时后续引用会 UnboundLocalError。已初始化 phase 并补错误日志。
- **非自选股实时报价永不刷新（真实 bug）**：_ensure_cached 在「缓存已存在但过期」时以 refresh(None) 只刷新自选/指数，
  行情页单独查看的股票会一直停留旧价。已改为始终 refresh(请求 codes)（refresh 内部会合并自选）。
  回归：test_stale_cached_quote_is_refreshed_even_when_not_in_watchlist。
- 日志：主源失败 info（尝试新浪）、双源失败 warning、刷新异常 warning；闭市/节假日轮询降到 ≥15s（原 3s 空转、无网络请求）。
- 删除不可达的 state=holiday 文案分支（_state 只返回 closed；LiveState 枚举也无 holiday）。

### 2.4 providers（Sina / Eastmoney / 共享 public_web）

- **东财换手率被丢弃**：build_canonical_bars 无条件把 turnover 置 0，东财 kline 的换手率（比例）被覆盖。
  已改为有该列则保留并转 float。回归：test_eastmoney_provider::test_turnover_from_kline_is_preserved。
- **重复日期/重复代码**：qfq/raw 合并前未去重会放大成笛卡尔积，universe 重叠分页会重复标的。
  已在 parse_sina_daily / parse_tencent_qfq / normalize_eastmoney_kline / universe 处去重。
  回归：test_sina_provider::test_duplicate_kline_dates_are_deduplicated / test_universe_deduplicates_overlapping_pages，
  test_eastmoney_provider::test_duplicate_kline_rows_are_deduplicated。
- **历史窗口时区**：Sina 用 datalen 覆盖「start→今天」，原先用本机时区 date.today()，跨时区/午夜可能少一天；
  已改为 Asia/Shanghai 的 _today_shanghai()。
- **并发声明不一致**：quota 写明并发 ≤2，但 provider 允许 max_workers 到 4；已钳制到 2。
  回归：test_sina_provider/test_eastmoney_provider::test_concurrency_is_clamped_to_the_declared_quota。
- **provider 数据可通过 quality gate**：新增集成测试用真实录制数据构 PanelData，run_quality_checks 无 error、隔离 0 行
  （覆盖 qfq 除权日 pre_close/涨跌停一致性）。见 test_sina_provider::test_provider_panel_passes_quality_gate。

## 3. qfq 跳点过滤与隔离行（审计）

- 当前 derive_adjustment 已包含供应商 qfq 毛刺过滤：跳变需超过噪声界（max(0.5%, 0.02/价格)）、需后续 1..5 根
  确认、且调整后日收益需在 ±11% 内，才接受为除权日；纯 rounding noise 不产生 corporate_action（有单测）。
- 隔离行：ingest.quarantine_bad_rows 只隔离 required/price/units/suspension/duplicate 行；limit 违规是 ERROR 但
  不隔离，会让整批 ingest 失败（设计取舍）。真实公网数据的 ST/停牌历史限制可能触发 limit 差异（见 §5-D）。

## 4. API 与 ui/src/api/types.ts 一致性（抽样，只读前端类型）

抽样 /health、/api/meta、/api/live/status、/api/data/status、/api/data/providers、/api/market/overview、
/api/jobs、/api/data/snapshots：TS 必需字段均存在，无缺失字段。差异（不破坏 UI 的结构化类型）：

- 冗余字段：LiveStatus.market.label（TS MarketClock 无）、/api/meta.api_version（TS Meta 无）、
  /api/market/overview.snapshot.created_at（TS SnapshotInfo 无）。冗余字段对 TS 结构化读取无害，保留兼容。
- MarketClock.next_open TS 声明 string|null，服务端实际总是 string；SnapshotStatus.start/end TS 声明 number|string，
  但无元数据快照理论上可能为 null（当前构建路径均有值）。建议后续统一类型或保证非空。
- /ws/live：服务端返回 {type,status,indices,quotes}，但 types.ts 无该消息类型，且 ui/src/api/client.ts 的 wsLiveUrl()
  当前没有任何 UI 使用（行情页走 /api/live/* 轮询）。属未使用的暴露面，建议要么补类型+消费，要么后续移除。

## 5. 剩余风险 / 未修（需后续决策）

| 编号 | 风险 | 影响 | 建议 |
|---|---|---|---|
| A | exchange-calendars 的 XSHG 日历目前 last_session=2026-12-31 | 之后日期靠 weekday 兜底，节假日判断失准 | 升级/更新依赖；clock 已有兜底不至于 500 |
| B | 增量 ingest 不重算历史 adj_factor：qfq 以最新日为基准，新增除权后旧行因子不会更新 | 存量历史复权序列在新除权后失真，55% 阈值质量检查不易发现 | 落库 qfq 收盘或在更新时重算受影响区间的 adj_factor（数据层设计） |
| C | qfq 过滤算法边界：窗口末端 1..5 根不能确认（漏除权）、value/current>2.5 阻断大比例送转、按 11% 判板对创业/科创/北交的真实除权日可能误阻断、<0.5% 股息漏检 | 个别公司行为缺失/延迟 | 后续接官方分红数据做权威复核；当前 source=SINA_APPROX 已标注 |
| D | ST 历史与真实涨跌停不可得：按当前名称 + 项目规则表（20260706 后 ST 10%）生成限价 | 限价列精度不足，不能用于精确涨跌停研究 | 接 ST 历史/官方涨跌停数据；docs/data-dictionary 已 TODO(verify) |
| E | Sina amount 为 volume×OHLC 均价估算；list_date=0；历史约 2000 bars | 成交额仅量级可用；新股覆盖率按全区间计会有缺口；更早区间不可取 | 已文档化；需要精确 amount/上市日时接其他数据源 |
| F | live 轮询无独立限速器：每次 refresh 最多 2 个公共请求、默认 3s，间隔即限速 | 公共接口压力小但无令牌桶 | 如需多客户端/多标的再引入 provider 级 limiter |
| G | /ws/live 未被 UI 消费、无 TS 消息类型 | 契约无人验证，后续接线易漂移 | 与 §4 一致：补类型+测试或移除 |

## 6. 验证

```text
uv run pytest -q tests/test_live_quotes.py tests/test_sina_provider.py \
  tests/test_eastmoney_provider.py tests/test_data_integrity.py   # 88 passed
uv run pytest -q -m 'not e2e and not bench and not network'       # 全绿
uv run ruff check python tests                                   # All checks passed
uv run ruff format --check python tests                          # 156 files formatted
uv run mypy python/quantcore                                     # Success (105 files)
```

测试全程不联网：live 测试用 FakeHttp/TestClient；provider 测试用 tests/fixtures/{sina,eastmoney} 录制样本。

## 7. 改动文件

- 修改：python/quantcore/realtime/clock.py、realtime/quotes.py、realtime/service.py、
  providers/public_web.py、providers/sina.py、providers/eastmoney.py、tests/test_live_quotes.py、
  tests/test_sina_provider.py、tests/test_eastmoney_provider.py
- 新建：docs/AUDIT-R3.md
- 未改（Lead 独占/范围外）：python/quantcore/trading_calendar.py、server/app.py、server/schemas.py、
  ui/**、pyproject.toml/uv.lock、docs/DESIGN-SPEC.md、README.md
