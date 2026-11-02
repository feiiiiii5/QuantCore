# 模拟交易（Paper Trading）模型

本地 A 股模拟撮合说明。**仅研究与模拟**：不连接券商、不发送真实委托、不访问网络；
成交全部基于会话引用的不可变本地快照（合成数据标注 SYNTHETIC）。

## 数据与量纲

- 价格：元（CNY），最小变动价位默认 0.01 元（`rules.min_price_tick`）。
- 成交量：**股（shares）**，与 `docs/data-dictionary.md` 的 volume 一致（不是“手”）。
- 会话逐日推进：`step()` 每调用一次前进一个交易日；当日只用该日 OHLCV，不做盘中撮合。

## 账户与 T+1

- 账户状态：现金、持仓（qty/available/avg_cost/last）、订单、逐笔成交、权益曲线。
- 买入成交后 `available=0`；下一交易日开盘前 `available=qty`（T+1）。
- 卖出只检查 `available`：当日买入的股份当日不可卖，提交时会报 T+1 错误。
- `equity = cash + Σ(qty × last)`；收盘后 `last` 更新为当日 close。

## 手数规则（买入）

复用 `paper/rules.canonical_buy_qty` 的板块/品种规则：

- 主板/创业板（MAIN/GEM）：100 股整数倍；科创板（STAR）：最少 200 股，1 股递增；
  北交所（BSE）：最少 100 股，1 股递增；ETF：100 份整数倍；可转债：10 张整数倍。
- 卖出不要求整手，但不得超过 `available`。

## 费用

- 逐笔成交分别计费，复用 `paper/rules.fee_breakdown`（回测 `CostModelConfig` 口径）：
  佣金（含最低 5 元）、印花税（仅卖出）、过户费（沪市）、交易所/证监规费。
- 部分成交时每笔成交单独计费，因此最低佣金可能被多次收取；`order.fees` 为各笔累加值，
  `session.trades[].fees` 仍为单笔费用。

## 成交规则

- 委托在提交后的下一个交易日尝试成交（`order.date < current_date`）。
- 市价单：以次日开盘价成交（受当日 high/low/涨跌停夹取）。
- 限价单：买入当 `low <= limit` 时触发，成交价 `min(open, limit)`；卖出当
  `high >= limit` 时触发，成交价 `max(open, limit)`；未触发则保持待成交。
- 停牌、开盘涨停（买）/跌停（卖）、一字线、无有效报价：按现有规则拒绝订单。
- 无滑点/盘口/排队模型，只用日线数据。

## 部分成交（参与率上限）

每个订单**每个交易日**最多成交：

```
cap = floor(当日 volume(股) × participation)
```

- 剩余数量 `remaining = qty - filled_qty`；当日可成交 `min(remaining, cap)`。
- 买单再按板块手数向下取整；取整后不足 1 手（或低于 STAR/BSE 最低股数）→ 当日不成交，
  订单保持 pending/partial，**不拒绝**，下一交易日继续尝试。
- 卖单不整手，且不超过 `position.available`。
- 成交量不足时只成交 cap 数量并生成一笔 trade；订单状态 `partial`，剩余数量后续交易日继续。
- 默认 `participation = 0.1`（当日成交量的 10%）。`participation = 1.0` 且成交量足够时，
  等价于旧版“一次性全成”行为。
- 若某笔成交金额超出可用现金，剩余部分按现有规则拒绝（`insufficient_cash`）。
- 部分成交后若后续交易日停牌/涨跌停/无有效报价，剩余部分按现有规则拒绝
  （`rejected`，已成交部分与 `fills` 保留）。
- 会话到达 end_date 时仍未成交完的订单保持 `partial`，不强制成交。

### 配置

配置位于会话 JSON 的 `config.execution.participation`（新会话默认写入 0.1）：

```json
{
  "config": {
    "costs": {"commission_rate": 0.0003, "min_commission": 5.0},
    "rules": {"main_lot": 100, "t_plus_one": true},
    "execution": {"participation": 0.1}
  }
}
```

- 旧会话 JSON 没有 `execution` 键时按默认 0.1 处理（向后兼容）。
- 合法范围 `(0, 1]`；非法值在引擎初始化时报 `PaperValidationError`。

## 订单状态与字段

- `status`：`pending`（待成交）、`partial`（部分成交）、`filled`（全部成交）、
  `cancelled`（用户撤单）、`rejected`（规则拒绝）。`pending`/`partial` 可撤单。
- `filled_qty`：累计成交量；`remaining_qty = qty - filled_qty`。
- `fill_price`：累计成交的**加权均价**（Σamount / filled_qty），不是最后一笔价格。
- `fill_date`：最近一笔成交（或拒绝）的日期。
- `fees`：累计费用；`fills`：逐笔成交明细
  `[{date, qty, price, amount, fees}]`（旧 JSON 无该字段时默认空列表）。
- 会话列表的 `pending_orders` 统计 `pending + partial` 的未完成订单数。
- 信号 CSV：`filled_qty` 为累计量、`fill_price` 为加权均价、`fees` 为累计费用。

## 与真实交易的差异

- 无真实盘口、订单簿、排队、滑点、冲击成本与成交概率模型；仅按日线 volume 比例近似容量。
- 无券商通道、无 T+0、无融资融券/期权/新股申购；不支持盘后固定价格等特殊申报。
- 涨跌停/停牌/ST/板块规则为本地近似，数值与官方规则细节可能不同；participation 是
  建模假设（默认 10%），不是交易所规则。
- 结算为即时本地记账（无 T+1 资金交收、无分红送转/除权处理）。
- 快照为历史数据回放，不是实时行情。

## 免责声明

本模块仅用于本地研究、策略验证与教学模拟，不构成任何投资建议；历史表现不代表未来收益。