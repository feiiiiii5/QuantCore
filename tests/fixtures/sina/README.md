# Sina / Tencent provider fixtures (recorded 2026-11-02)

Recorded from the public quote endpoints on 2026-11-02 (Asia/Shanghai) for offline tests.
The default test suite never touches the network.

| file | provenance |
|---|---|
| `universe_page1.json` | Sina `Market_Center.getHQNodeData` page 1, node=hs_a (80 rows, BSE names) |
| `universe_page4.json` | same endpoint page 4 (still BSE; kept for pagination samples) |
| `universe_page8.json` | same endpoint page 8 (SH main-board names) |
| `kline_sh600000.json` | Sina `CN_MarketData.getKLineData` sh600000, scale=240, datalen=120 (2026-05-07..2026-10-30, **volume in shares**) |
| `index_kline_sh000001.json` | Sina index kline sh000001, datalen=60 (calendar source) |
| `qfq_sh600000.json` | Tencent `fqkline/get` sh600000 qfq (2026-01-05..2026-10-30; **volume in lots**, only close is used) |

Unit / data notes:

- Sina kline returns `day, open, high, low, close, volume` and **no amount**; the provider
  estimates amount = volume x mean(OHLC) for magnitude checks only (documented in
  `docs/data-dictionary.md`).
- The recorded 600000 window contains a real ex-dividend day on 2026-07-16 (factor 0.9549 -> 1.0),
  which the tests use to verify the approximation; fixtures are trimmed copies of the responses.
