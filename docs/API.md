# API — Python / qcore

## 顶层
```python
import quantcore
quantcore.__version__       # "0.1.0"
quantcore.engine_backend()  # "cpp"（生产验证必须为 cpp）
quantcore.require_cpp()     # 扩展缺失时抛 RuntimeError
```

## qcore（`quantcore._qcore`，pybind11）
```python
from quantcore import _qcore as qc
panel = qc.Panel.open("snap_xxx.qpanel")
print(panel.n_sec, panel.n_time, panel.dates[:3], panel.field_names())
view = panel.field("close")          # 零拷贝 numpy 视图（布局见 view.layout）
print(view.shape, view.layout)       # (n_sec,n_time) 或 (n_time,n_sec)
```
- `PanelWriter(n_sec, n_time, dates, securities)`；`add_field(name, layout, np.ndarray)`；`write(path)`。
- `kernels.*`：rolling/cross/indicators（输入/输出 `numpy.ndarray[float64]`）。
- `Calendar.weekdays(start, end)` / `is_trading_day` / `next` / `prev`。
- `BacktestConfig`、`Engine(panel, config)`、`Engine.run(weights, cancel)`：
  - `weights`：`(n_time, n_sec)` float64；非 NaN 行 = 调仓日；NaN = 不调仓；权重为目标市值占比。
  - 返回 dict：`dates/equity/cash/market_value/trades/metrics/reasons/engine_version/seed`。

## Python 平台
```python
from quantcore.data.synthetic import SyntheticProvider
from quantcore.snapshot import build_snapshot
from quantcore.backtest import run_backtest

provider = SyntheticProvider(securities=200, years=5, seed=42)
build_snapshot(provider, "data/snapshots/demo")
result = run_backtest("data/snapshots/demo", strategy="ma_cross",
                      start="2021-01-01", end="2025-12-31")
print(result.metrics)
```
- 数据：`DataProvider` 统一接口；Synthetic/LocalFile/Tushare/AKShare/mootdx；快照不可变、内容寻址。
- 策略：声明式条件 / 面板目标权重 / 事件回调；7 个模板；参数 JSON Schema。
- 实验：元数据含策略 hash、参数、快照 hash、引擎版本、seed；`qc replay <pack>` 可复现。

## CLI
```
qc data update --provider synthetic|tushare|local
qc snapshot build --dataset NAME
qc backtest run --strategy NAME --start YYYY-MM-DD --end YYYY-MM-DD
qc sweep run --strategy NAME --grid grid.json
qc check lookahead --strategy NAME
qc replay <experiment-pack>
qc serve [--port 0]
qc bench
```
所有命令输出 JSON 时字段稳定；`--json` 便于脚本。

## 因子表达式 DSL（`_qcore.Expression`）
```python
expr = _qcore.Expression.parse("rank(ts_mean(close,5)/ts_mean(close,20))")
expr.eval(panel, sec, time)        # 单点
expr.eval_cross(panel, sec, time)  # 单点，rank/zscore 用 t 时刻全截面
_qcore.evaluate_panel(panel, expr, layout="sec_time")  # 全面板 numpy
expr.explain()                     # DAG/CSE 可读摘要
```
- 语法：数字、字段（open/high/low/close/volume/amount/returns）、`+ - * /`、比较、and/or/not；
  `ts_mean/ts_std/ts_sum/ts_min/ts_max/ts_rank(x,n)`、`rank/zscore`、`delay(x,n)`、`abs/log/sqrt/min/max/pow`。
- NaN 统一传播；除零/log 非法/sqrt 负/溢出 → NaN；ts_* 要求完整窗口且无 NaN；ts_std 为样本 std（ddof=1）；
  rank/ts_rank 为 average-rank 百分位；zscore 用截面样本 std；字段只读到 t（delay/rolling 不读未来）。
- 窗口参数必须是整数字面量（≤5000）；非法语法抛 `ValueError`（含 1-based 位置）。
- 注意：当前 `evaluate_panel` 每次重新编译（µs 级）；全面板性能优化列入 M7。
