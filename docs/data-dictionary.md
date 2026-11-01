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
