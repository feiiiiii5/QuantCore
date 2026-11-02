# data-dictionary — 数据集 schema（V1 设计，分阶段接入）

## 证券主数据
| 字段 | 类型 | 说明 |
|---|---|---|
| sec_id | int32 | 稳定内部 ID |
| code | str | 当前代码（6 位） |
| exchange | str | SH/SZ/BJ |
| name | str | 当前名称 |
| board | enum | MAIN/GEM/STAR/BSE |
| list_date | Date | 上市日 |
| delist_date | Date? | 退市日 |
| sec_type | enum | STOCK/ETF/CB |
| st_periods | list[(start,end)] | ST/*ST 历史 |
| code_changes | list[(date, old, new)] | 改码历史 |

## 日线行情（原始价）
open/high/low/close: Px；volume: Qty（股）；amount: Money（元）；adj_factor: double；limit_up/limit_down: Px；suspended: bool；turnover: double；total_shares/float_shares: Qty。

## PIT 财务
保留全部披露版本：ann_date/f_ann_date/end_date/report_type/update_flag + 字段值；默认公告日后下一交易日起可用（可配）。

## 公司行为
分红/送转/配股：ann_date、record_date、ex_date、pay_date、cash_per_share、split_ratio、rights_ratio/price。

## 指数与行业
指数成分/权重历史；行业分类历史；基准指数（优先全收益）。

## 快照清单
snap_<hash>/manifest.json：来源、版本、摄取时间、质量摘要、schema 版本、.qpanel 哈希。

## 数据源口径（provider → canonical，含实测校验）

### 日线单位换算

| provider | 原始接口 | volume 原始单位 | 归一化 | amount 原始单位 | 归一化 | 价格口径 |
|---|---|---|---|---|---|---|
| tushare | Pro `daily` | 手 | ×100 → 股 | 千元 | ×1000 → 元 | 未复权原始价 |
| sina | `CN_MarketData.getKLineData` | 股 | 原样 | 无该字段 | 按 volume × OHLC 均价**估算**（仅量级/容量用途，TODO(verify)） | 未复权原始价 |
| eastmoney（备用） | `push2his` kline（klt=101） | 手 | ×100 → 股 | 元 | 原样 | fqt=0 未复权原始价 |
| tencent qfq | `fqkline`（qfq） | 手 | 仅取前复权收盘价用于因子推导 | — | — | 前复权价 |

实测校验（录制于 2026-11-02，样本见 `tests/fixtures/sina` 与 `tests/fixtures/eastmoney`）：

- 东财 600000 2026-10-20：`volume=605133` 手 → `60,513,300` 股；`amount=589,321,380` 元；
  `amount / volume = 9.74`，落在当日 `[low 9.68, high 9.86]` 区间内，证明 ×100 换算正确
  （若不换算，隐含均价 973.8，超出区间 100 倍，会被体检的 volume/amount 量级检查抓到）。
- 新浪 600000 同日 `volume=60,513,255` 股，与实时成交量一致，**无需换算**。
- 新浪 amount 为估算值（591,365,800 元），与东财真实成交额相差约 0.3%；仅用于量级/容量过滤，
  不能当作真实成交额参与精确成本/冲击建模（TODO(verify)：接入带 amount 的历史源后替换）。
- 2026-07-16 为 600000 的除权日（实测复权因子 0.9549 → 1.0），估算每股现金分红 0.4044 元，
  `source=SINA_APPROX`。

### 复权因子与公司行为（近似）

- `adj_factor` = 前复权收盘 / 原始收盘（新浪日线 + 腾讯 qfq；东财备用源用 fqt=1 序列），
  单调非减；除权日前后因子跳变。
- 跳变超过四舍五入噪声界 `max(0.2%, 0.02/价格)` 视为除权除息日：小跳变估算
  `cash_per_share`，大跳变（≥1.2）估算 `split_ratio`；行标记 `SINA_APPROX` /
  `EASTMONEY_APPROX`。
- 除权日 `pre_close = 前收 × 因子(t-1)/因子(t)`（交易所除权参考价口径），
  `limit_up/limit_down` 由该 pre_close 派生，因此体检的涨跌停自洽检查可通过。
- **TODO(verify)**：公司行为是推导值而非官方分红公告；现金分红与送转拆分只是粗略估计，
  不可用于精确分红再投资核算。需要精确口径时应接入官方分红数据（含 ann_date/record_date）。

### 交易日历与缺失语义

- 新浪：上证指数 `sh000001` 日线日期；东财：指数 `1.000001` 日线日期。
- 历史上限约 2000 根日线（约 2018-07 起，`datalen=2000`）；请求更早的 start 会得到明确的
  `ProviderError`，不会静默截断。
- 停牌日在 provider 输出中没有行（不补 `suspended` 行）；数据体检把缺失日计为"缺口"。
  如需停牌标记需另行接入停牌数据（TODO(verify)）。

### 涨跌停 / ST 规则

- 板块按代码前缀推断：60x/00x → MAIN、30x → GEM、68x → STAR、4/8/92x → BSE；
  限价比率与 `data/synthetic_rules.py`、`quality/checks.py` 的规则表一致。
- **TODO(verify)**：ST 5% → 10% 切换日期（项目规则表写为 20260706）沿用现有规则，
  真实交易所规则需复核；provider 不抓取 ST 变更历史，`st` 仅按当前证券名称是否含 "ST" 标记。

### 数据体检（`GET /api/data/integrity`、`qc data integrity`）

- `coverage`：按"每个标的上市日之后"的应有交易日计算 expected_cells，避免新股/次新股拖低覆盖率。
- `checks`：覆盖率、缺口、OHLC 自洽、volume/amount 量级、涨跌停一致性、复权连续性、跨源抽样
  （默认离线跳过，传入回调才启用）。
- `accuracy`：`ohlc_violations`、`volume_amount_mismatch`、`limit_violations`、
  `adjustment_breaks` 四个计数；具体阈值见 `python/quantcore/data/integrity.py`。
- `cross_source` 默认 `checked=0` 并在 note 说明"离线未启用"，不会联网。
