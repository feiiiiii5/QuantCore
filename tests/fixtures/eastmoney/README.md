# Eastmoney provider fixtures (recorded / derived samples)

These files are network recordings / derived samples used by
`tests/test_eastmoney_provider.py`; the default test suite never touches the network.

| file | kind | provenance |
|---|---|---|
| `universe.json` | recorded | `push2.eastmoney.com/api/qt/clist/get` page 1 (SH main-board sample, public web `ut` id, browser UA/Referer), recorded 2026-11-02 |
| `kline_1.600000_fqt0.json` | recorded | `push2his.eastmoney.com/api/qt/stock/kline/get` 600000, klt=101, fqt=0, 2026-10-20..2026-10-30 |
| `kline_1.600000_fqt1.json` | derived | fqt=1 counterpart of the recorded window (qfq == raw because that window has no corporate action) |
| `kline_1.600000_fqt0_div.json` | derived | constructed 5-day window around a 0.50 CNY cash dividend (ex-date 2026-06-25) |
| `kline_1.600000_fqt1_div.json` | derived | constructed fqt=1 (qfq) counterpart of the `_div` file for deterministic corporate-action break tests |
| `kline_1.600000_fqt0_gap.json` | derived | recorded 600000 fqt=0 with 2026-10-22/23 rows removed to model a suspension gap |
| `kline_1.600000_fqt1_gap.json` | derived | fqt=1 counterpart of the gap sample |
| `kline_1.600000_fqt0_error.json` | derived | Eastmoney error-contract sample (`rc=102`) for the error path |
| `kline_1.601999_fqt0.json` | derived | empty-data contract sample (`data:null`) for the empty path |
| `index_kline.json` | derived | index kline used as the trading calendar (dates from the recorded 600000 window; the index endpoint was rate-limited during recording) |

Unit conventions (verified against the recorded sample and cross-checked):
`volume` is in lots (手, x100 shares) in the raw endpoint and is multiplied by 100 to
canonical shares; `amount` is CNY (元); prices are raw (unadjusted) when fqt=0.
`srv` values are volatile server ids and carry no meaning.

Live recording was rate-limited part-way through (the Eastmoney edge returns
`curl: (52) Empty reply from server` after a handful of requests), so the fqt=1 and
index files are derived samples; re-record them with the documented URLs when the
endpoint is reachable again.
