# QuantCore

[简体中文](README.md) · English

**Turn an A-share strategy idea into an experiment you can compare, reproduce and investigate further.**

QuantCore is a local-first quantitative research workbench with a **C++20 backtesting core**.
It connects data checks, strategy backtests, experiment comparison, robustness analysis and paper accounts in one interface. Data and experiment records stay on your machine.

[![CI](https://github.com/feiiiiii5/QuantCore/actions/workflows/ci.yml/badge.svg)](https://github.com/feiiiiii5/QuantCore/actions/workflows/ci.yml)
[![C++20](https://img.shields.io/badge/core-C%2B%2B20-00599C)](cpp/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[Run locally](#run-locally) · [Architecture](docs/ARCHITECTURE.md) · [API](docs/UI-API.md) · [Validation record](docs/acceptance-report.md)

![Experiment comparison: normalized equity, metric differences and research assumptions](docs/screenshots/research-comparison.png)

*The examples use SYNTHETIC data. QuantCore currently supports research and simulation, with no broker connection or real order submission. The interface and most documentation are in Chinese.*

## Follow an idea through the research process

For example, investigate whether stocks with strong recent performance continue to outperform:

1. **Prepare data.** Start with the built-in synthetic demo or import your own data, then inspect coverage, gaps and price anomalies.
2. **Define a strategy.** Choose a momentum or moving-average template and adjust its parameters. Expressions and local strategy plugins support more advanced work.
3. **Run a backtest.** Set dates, initial capital, costs and execution rules; inspect equity, drawdown, metrics and individual trades.
4. **Compare experiments.** Reuse an experiment's saved data and configuration, then compare normalized curves, metric differences and assumptions.
5. **Check sensitivity.** Run cost sensitivity or Monte Carlo on saved experiments, or select multiple experiments for PBO. Factor diagnostics, parameter sweeps and fixed-parameter time splits are configured separately; paper accounts support daily replay.

## Keep the assumptions beside the results

**See what changed.** Comparison normalizes equity using recorded initial capital and identifies differences in data, dates, capital, costs and rules. Missing conditions are marked unknown.

**Continue with the same data.** Reusing an experiment reads its snapshot or persisted panel, retains configuration and records the new experiment's parent. A parameter change can be distinguished from a data change.

**Keep a record you can inspect.** Experiments save strategy parameters, engine version, data references or panels, results and reports. Replay reruns an experiment and checks equity, trades and metrics; differences across versions still need investigation.

## Capabilities

| Area | What you can do |
|---|---|
| Market and screening | Indices, watchlists, price charts and expression screening; optional public live quotes with explicit data status |
| Data | Import, coverage and gap checks, price consistency checks, snapshots and data fingerprints |
| Strategies and backtests | Templates, expressions and local plugins; C++ daily-bar backtests with costs, T+1, lot and execution rules |
| Experiments | Saved parameters and data, parent lineage, normalized comparison, assumption differences, replay checks and reports |
| Research | Factor IC, groups and decay; parameter sweeps; fixed-parameter time splits; industry attribution; PBO, cost sensitivity and Monte Carlo |
| Paper accounts | Historical daily replay, orders and holdings, T+1, partial fills, signal CSV export and multi-strategy portfolios |

Cost sensitivity treats fee multipliers as separate scenarios and displays returns, Sharpe, drawdown and fees in yuan:

![Cost scenarios, return sensitivity and metric details](docs/screenshots/cost-sensitivity.png)

## Run locally

Source runtime: **macOS or Linux**, Python 3.12, [uv](https://docs.astral.sh/uv/), a C++20 compiler, CMake ≥ 3.26, Ninja, Node.js ≥ 20 and pnpm.
The interface supports light/dark themes, beginner/advanced modes and mobile layouts.

```bash
git clone https://github.com/feiiiiii5/QuantCore.git
cd QuantCore

# Install Python dependencies and compile the C++ extension
uv sync --frozen --python 3.12 --default-index https://pypi.org/simple

# Install and build the interface
pnpm -C ui install --frozen-lockfile
pnpm -C ui build

# Generate synthetic data, a snapshot and a first backtest report
uv run --no-sync qc demo --data-root data

# Open the local workbench using the same data directory
uv run --no-sync qc serve --data-root data --port 8000 --open
```

Dependency installation needs internet access. Once installed, the synthetic demo and local research can run offline. Example data is labelled `SYNTHETIC`.
The server binds to `127.0.0.1`. Open Experiments to inspect the demo result, then reuse its data and parameters for another run.

See the [quick start](docs/QUICKSTART.md) and [local testing guide](docs/LOCAL-TESTING.md) for setup, real-data import and troubleshooting.

## Native core and application architecture

| Layer | Technology and responsibility |
|---|---|
| Native core | **C++20 `qcore`**: `.qpanel` I/O, native numerical kernels, daily event-driven backtesting, ledger and cost calculations; exposed through pybind11 |
| Application | Python / FastAPI: data ingestion, strategy orchestration and expression evaluation, experiments, research, paper accounts and HTTP/WebSocket APIs |
| Interface | TypeScript / React 19 / Vite: market, strategy, backtest, experiment and research workflows |
| Local storage | Parquet data, DuckDB queries, SQLite state and `.qpanel` engine snapshots |

Production backtests require the native engine and report an error if the extension is missing. The Python reference backtester is test-only; paper matching and some research calculations remain in Python.

### Inspectable validation

Local validation on 2026-11-06: **383 Python tests passed / 2 skipped**, **20 frontend tests passed**, **19/19 real-server browser tests**, **6/6 C++/reference differential tests**, and the existing C++ verification, type and build checks.
The [validation report](docs/acceptance-report.md) records scope, reproduced failures and unverified areas. The badge above links to the current CI state.

## Data and current scope

Network data access is disabled by default. Optional public historical and live sources have depth, licensing and adjustment/corporate-action approximation limits. Live quotes are display-only and are not a licensed L2 feed.
Walk-forward analysis currently uses fixed parameters over time splits. Robustness metrics are research tools. Windows currently has Python smoke coverage and an unsigned client shell; the full C++ backend is not supported there.

The current phase focuses on local research and testing; production deployment has not been validated. Historical performance does not predict future returns, and results are not investment advice.
See [data licences](docs/DATA-LICENSES.md), [engine semantics](docs/engine-semantics.md) and [rule sources](docs/rules-sources.md).

## Documentation and contributing

- **Get started:** [tutorial](docs/TUTORIAL.md), [quick start](docs/QUICKSTART.md), [local checks](docs/LOCAL-TESTING.md)
- **Understand the system:** [architecture](docs/ARCHITECTURE.md), [strategy guide](docs/strategy-guide.md), [API](docs/UI-API.md)
- **Inspect evidence:** [validation](docs/acceptance-report.md), [progress](docs/PROGRESS.md), [performance notes](docs/PERFORMANCE.md)
- **Contribute:** [contributing guide](CONTRIBUTING.md), [issues](https://github.com/feiiiiii5/QuantCore/issues)

Code is licensed under [Apache-2.0](LICENSE). Third-party dependencies and data have their own terms; see [data licences](docs/DATA-LICENSES.md).
