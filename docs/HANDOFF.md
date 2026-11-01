# HANDOFF — QuantCore 迁移会话交接

> 生成时间：2026-11-02 07:50（Asia/Shanghai）
> 交接目标：在**新的会话/新的执行者**中继续 QuantCore；**接下来的工作只能在
> `/Users/fei/Desktop/QuantCore` 工作区内完成**。
> 生成 handoff 前已验证的代码 HEAD：`4f2820c`（`docs: all 117/117 features complete with documented limitations`）；
> 本文件及文档一致性修正会在其之后提交，实际以 `git log -1 --oneline` 为准。

---

## 0. 先做这五件事

```bash
cd /Users/fei/Desktop/QuantCore
git status --short                 # 期望干净；有未提交改动先弄清来源
git log --oneline -10              # 确认 HEAD 和最近提交
python3 - <<'PY'
import json
d = json.load(open("docs/features.json"))
print(sum(1 for f in d["features"] if f["passes"]), "/", len(d["features"]))
PY
gh run list --repo feiiiiii5/QuantCore --limit 3
```

当前基线（本次交接时）：

- 仓库：**https://github.com/feiiiiii5/QuantCore**（public，Apache-2.0）
- 分支：`main`；remote `origin` 为 `git@github.com:feiiiiii5/QuantCore.git`
- 工作区：干净
- 功能门禁：`docs/features.json` **117/117**（M0–M10 全部条目 true）
- CI：最近完整 run **41350659878**，5 个 job 全 success：
  `test (macos-latest)`、`test (ubuntu-latest)`、`windows-smoke`、`ui`、`desktop-windows-package`
- 本地最终门禁：`make ci-local` 通过；`make e2e` 18/18 通过

> **重要**：117/117 表示“功能门禁全部有代码 + 证据”，**不等于**真实 vendor 实时行情、
> 签名公证安装包或生产实盘已完成。限制见第 8 节，交接时必须保留这些限制。

---

## 1. 工作边界（必须遵守）

1. **只改 `/Users/fei/Desktop/QuantCore`**。不要读写或改动 `/Users/fei/Desktop/申请季`，
   也不要在申请季目录下生成临时文件、缓存或日志。
2. 本项目**只做研究与模拟**：
   - 不实现真实下单/真实券商连接；`BrokerGateway` 默认禁用；
   - 不把合成数据或回测结果写成真实市场结论；
   - 合成数据必须带 `SYNTHETIC` 标签。
3. 网络默认关闭：Tushare/ AKShare/ mootdx 需要显式网络权限和凭据；没有 Token 时
   只用 Synthetic + fixture。凭据不得写入代码、日志、handoff 或提交。
4. 不提交运行期数据：`data/`、`experiments/`、`ui/dist/`、`dist/`、`node_modules/`、
   `.venv/`、`*.qpanel`、`*.sqlite*`、`*.parquet` 均被 `.gitignore` 忽略；不要 `git add -A`。
5. 提交走 Conventional Commits；只 stage 明确路径；push 前必须复跑门禁。
6. 文档里的 `TODO(verify)` 规则（ST 幅度、盘后固定价历史、新股/退市整理、分红个税、
   部分费率）未核实前不要写成已验证事实。

---

## 2. 环境与快速启动

已验证的开发机环境：

- macOS arm64；项目 `.venv` 为 **Python 3.12**（通过 `uv` 管理）。
  ⚠️ 系统 `python3` 可能是 3.11；**始终用 `uv run ...`**，不要直接 `python3` 跑项目测试。
- `uv 0.13.6`、Node `v23.11.0`、pnpm `12.14.0`、CMake `4.4.2`、Ninja `1.13.0`
- Playwright E2E 需要本机 **Chrome**（`make e2e` 使用 system Chrome channel）
- Electron smoke 需要 `desktop` 依赖；当前环境可能设置了 `ELECTRON_RUN_AS_NODE=1`，
  启动 Electron 时要用 `env -u ELECTRON_RUN_AS_NODE ...`

### 全新环境

```bash
cd /Users/fei/Desktop/QuantCore
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
make setup                 # uv python 3.12 + uv sync --all-extras + build C++/extension
pnpm -C ui install         # 前端依赖
pnpm -C ui build           # 构建 ui/dist（qc serve 需要）
```

### 每天开发

```bash
cd /Users/fei/Desktop/QuantCore
make build
make test                  # pytest + ctest
make lint                  # ruff check/format + mypy + clang-format（若安装）
make verify-cpp            # C++ backend= cpp / 差分 / 性能门禁
make e2e                   # UI Vitest + 隔离 qc serve + Playwright 18
make ci-local              # 本地完整门禁
```

### 启动工作台

```bash
cd /Users/fei/Desktop/QuantCore
uv run qc serve --port 8000 --open
```

- `qc serve` 同时托管 FastAPI `/api`、WebSocket 与 `ui/dist`；
- 只绑定 loopback；启动 token 可来自 `QC_SERVER_TOKEN`，`--open` 会带 token URL；
- 前端开发可用 Vite dev server，但需要 proxy `/api`、`/ws`、`/health` 到 8000
  （详见 `ui/vite.config.ts` 与 `docs/UI.md`）。

### 合成数据 + 快照（干净复现）

```bash
uv run qc data update --provider synthetic --n-sec 200 --start 2020-01-02 --end 2024-12-31
uv run qc snapshot build
uv run qc backtest run --template dual_ma
```

---

## 3. 当前验证基线（交接证据）

本次运行实际得到：

```text
pytest       196 collected / 194 passed / 2 skipped
ctest        95/95 passed
UI vitest    7 passed（4 files）
Playwright   18/18 passed（真实 qc serve + Chrome）
ruff/format/mypy  全绿（mypy 87 files）
make ci-local     通过
make e2e          通过
make verify-cpp   通过（C++ backend、差分 6/6、性能门禁）
```

`make e2e` 会构建 UI、用临时 data/experiments 启动隔离 `qc serve`，不污染工作区；
它运行 `pytest -m e2e`、UI Vitest 和 Playwright，全部通过。

CI 覆盖：

- Ubuntu + macOS：完整 C++/Python/UI 测试、lint、C++ verify；
- Windows：`windows-smoke`（providers/strategy/synthetic 纯 Python）+
  `desktop-windows-package`（Electron unsigned zip 构建）；
- Playwright E2E **不在 GitHub CI**，仅本地 `make e2e`（需 Chrome）。

---

## 4. 架构地图

```text
React 19 + Vite UI (ui/)
   │ 同源 HTTP + WS，Bearer token，loopback
   ▼
FastAPI qc-server (python/quantcore/server)
   │  /api/market /screener /strategies /backtest /jobs
   │  /experiments /data /research /paper /onboarding
   ▼
SQLite state (jobs/snapshots/datasets/meta, WAL) + job worker（协作取消）
   │
Provider → ingest/quality → Parquet + DuckDB → snapshot(manifest + .qpanel)
   │
策略生成 (n_time, n_sec) 目标权重 → C++ Engine（规则/费用/T+1/账本/trace/metrics）
```

- **C++ `qcore`**：固定点 `Px/Money=int64 1e-4`、`Qty=int64`；`.qpanel` v1 mmap；
  panel/kernels/expression/engine/analytics；pybind11 暴露 `_qcore`。
- **Python 控制面**：数据 provider/ingest/quality/snapshot、策略 DSL/模板、实验、
  研究、paper、服务、CLI；生产回测必须走 `_qcore.Engine`，纯 Python 参考实现只在 `tests/reference`。
- **UI**：React 19 + Vite + TypeScript；ECharts/lightweight-charts/Monaco 本地打包；
  TanStack Query/Table/Virtual；8 个主页面 + 设置（实际路由见 `ui/src/App.tsx`）。
- **安全边界**：同源、Bearer token、Host/Origin 校验、无 CORS、loopback only；
  策略插件是本地信任模型，静态 AST 审计不是多租户安全边界；
  自定义/插件策略可通过子进程 worker 隔离运行（CPU/文件大小限制），但不是强沙箱。

---

## 5. 关键文件地图

### C++

- `cpp/include/qcore/`：公共头（types/panel/kernels/engine/expr/analytics/sweep/tpool…）
- `cpp/src/core|panel|kernels|expr|sim|analytics|sweep|bindings/`
- `cpp/tests/`：95 个 Catch2 tests；`ctest --test-dir build/cmake --output-on-failure`
- `cpp/bench/`、`cpp/fuzz/`
- 构建：`CMakeLists.txt` + scikit-build-core（`pyproject.toml`）；`make build` 重装扩展

### Python（`python/quantcore/`）

- `backtest/`：config/engine/sweep/result；`engine.py` 有 `run_backtest` 和
  `run_backtest_batch`（C++ `qc::parallel_sweep`）
- `data/`：`panel.py`、`synthetic.py`、`minute.py`、`catalog.py`、`store.py`、parquet/DuckDB
- `providers/`：synthetic/local/tushare/akshare/mootdx；`tushare.py` live 路径已用 fake Pro 测试
- `ingest/`、`quality/`、`snapshot/`：快照内容寻址、manifest、PIT 元数据、`.qpanel`
- `strategy/`：DSL、模板、plugin 发现/审计、`worker.py` + `sandbox_worker.py`
- `jobs/`：SQLite 任务队列/worker/取消/恢复；`server/`：FastAPI 路由 + WebSocket + 安全
- `experiments/`：store/runner/replay/report；`report_pdf.py`：本地 Chrome PDF（可选）
- `paper/`：虚拟账户/撮合/持久化/组合/规则；`research/`：因子/sweep/robustness 等
- `cli.py` / `cli_serve.py`：`qc` 命令入口
- `templates/`：7 个策略模板

### UI

- `ui/src/pages/`：Market/Screener/Strategy/Backtest/Experiment/Research/Paper/Data/Settings
- `ui/src/components/`：KLineChart、VirtualTable、JobProgress、Onboarding、ErrorBoundary、toast/notifications 等
- `ui/src/api/`：`client.ts`、`queries.ts`、`types.ts`；`ApiError`、Bearer token 处理
- `ui/e2e/app.spec.ts`：18 条 Playwright；`ui/src/**/*.test.tsx`：Vitest 7 条
- `ui/dist/` 被 `qc serve` 托管；构建后才会生效

### 桌面/脚本/文档

- `desktop/`：Electron dev shell + unsigned macOS/Windows 打包配置；`make desktop-smoke`
- `scripts/`：`verify_cpp.py`、`perf_gate.py`、`sbom.py`、`audit.py`、`release.sh`、
  `e2e.sh`、`desktop_smoke.sh`、`bench.py`
- `docs/`：入口是 `docs/HANDOFF.md`（本文件）、`docs/features.json`、
  `docs/acceptance-report.md`、`docs/PROGRESS.md`、`docs/UI-API.md`、`docs/ARCHITECTURE.md`、
  `docs/engine-semantics.md`、`docs/RELEASE.md`
- `docs/screenshots/`：UI 截图（行情/回测/研究/模拟/暗色/移动端/稳健性等）

---

## 6. 功能完成状态（M0–M10，117/117）

逐项证据以 `docs/features.json` 为准；这里只列面上结论和关键 caveat：

| 里程碑 | 状态 | 关键内容 / 证据 |
|---|---|---|
| M0 底座 | ✅ | Makefile、wheel、`.qpanel`、pybind11 zero-copy、CI matrix（macOS/Ubuntu/Windows smoke） |
| M1 C++ 基础 | ✅ | types/calendar/tpool/panel/kernels（含 neutralize）/指标/零拷贝绑定；ctest 95 |
| M2 数据中心 | ✅ | Synthetic/LocalFile/Tushare fixture+live 代码路径/AKShare/mootdx；Parquet+DuckDB+SQLite；快照质量/PIT |
| M3 回测引擎 | ✅ | 事件驱动；规则/费用/T+1/手数/涨跌停/停牌/除权除息/trace/指标；风险限制、基准比较；差分 6/6 |
| M4 SDK/CLI/策略 | ✅ | DSL 17 用例、7 模板、lookahead、HTML+可选 PDF、子进程 sandbox worker、C++ parallel sweep、CLI/replay |
| M5 服务层 | ✅ | FastAPI v2、SQLite job 队列/取消/恢复、WebSocket、安全头、GZip、本地通知 |
| M6 UI V1 | ✅ | 八页工作台真实接线；Playwright 18；浅/深色、密度、移动端、性能预算 |
| M7 研究工具 | ✅ | IC/RankIC/ICIR、分层/衰减、因子相关、grid/random sweep、滚动、归因、DSR/PBO、成本敏感性、MC、容量 |
| M8 V2 数据 | ✅ 大部分 | 证券资料、PIT 财务、ETF/可转债 canonical+paper 手数、合成分钟线、V2 dataset catalog；C++ 回测仍日线/board 手数 |
| M9 模拟交易 | ✅ | 虚拟账户、历史回放、委托撤单/成交、T+1/费用、信号 CSV、提醒、本地插件、只读多策略组合、服务端模拟时钟连续推进；**无真实 vendor feed** |
| M10 发布 | ✅ 大部分 | wheel/UI/文档/许可、CycloneDX SBOM+pip-audit、release/perf gate、Electron dev shell、unsigned macOS/Windows zip；无签名公证/安装运行验证 |

---

## 7. 已知限制与风险（必须保留，不要重新包装成“已完成”）

1. **没有真实下单**：这是研究/模拟系统；`BrokerGateway` 默认禁用，UI/报告带免责声明。
2. **Tushare live 未做真实网络验证**：
   - live `daily` / `fina_indicator` / `dividend` 代码路径已实现；
   - `tests/test_tushare_live.py` 用进程内 fake Pro API 做契约测试；
   - 真实 Token/网络、限流配额、字段差异仍未验证。
3. **分钟线是合成视图**：
   - `python/quantcore/data/minute.py` 由日线拆成 5 个 intraday bucket；
   - API `/api/market/minute-bars` 与行情页“分钟”面板可用；
   - C++ 引擎仍是日线，不提供分钟级回测/撮合。
4. **ETF/可转债语义有限**：
   - 数据模型/API/paper 手数（ETF 100、CB 10）已支持；
   - C++ 回测仍按 board 手数，不能宣称 ETF/CB 的完整回测规则。
5. **桌面包不是生产安装包**：
   - unsigned macOS/Windows zip 可构建；macOS 打包 app 做过 headless 加载 UI 的 smoke；
   - Windows zip 仅 CI 构建，未在 Windows 安装/运行验证；
   - 后端不随包捆绑（默认需本地 `qc serve`，或 `QC_DESKTOP_URL` 指向运行中服务）；
   - 无签名、无公证、无自动更新。
6. **未做全市场规模/性能验证**：
   - 5500×20y、10000 组 sweep、峰值 RSS、覆盖率统计没有实测；
   - 现有性能门禁是小集（`docs/performance-baseline.json`，`make perf-gate`）。
7. **研究口径是近似**：
   - 归因是行业 FIFO 近似；DSR/PBO/成本敏感性/MC/容量是研究近似；
   - 规则 TODO(verify) 仍需外部官方来源核实（`docs/rules-sources.md`）。
8. **文档漂移**：
   - `docs/ARCHITECTURE.md` 仍有“七导航”“TODO 子进程资源限制”等历史表述（实际已有 8 页 + worker）；
   - `docs/RELEASE.md` 的发布清单写于打包功能之前，`desktop/README.md` 已同步但 RELEASE 可能仍提“未验证”；
   - 以 `docs/HANDOFF.md` + `docs/features.json` + 当前代码/测试为准；发现冲突时更新文档，不要沉默。
9. **不要提交运行期数据/大文件**：
   - `data/`、`experiments/`、`dist/`、`ui/dist/`、`node_modules/`、`.venv/` 都是本地产物；
   - `dist/desktop` 里有 unsigned zip，但不进 git。

---

## 8. 推荐下一步（只有当用户明确要求继续开发时）

优先级从高到低：

1. **真实 vendor 实时 feed（M9 限制）**
   - 接一个真实 A 股实时行情源需用户提供网络/Token/许可；
   - 先做 provider 接口 + 录制 fixture + 明确 `allow_network`/Token 门禁；
   - paper 侧保持无真实下单。
2. **签名/公证安装包**
   - macOS Developer ID + notarization；Windows code signing；
   - 把后端/UI 打包策略写清楚（当前 Electron 只是客户端壳）。
3. **真实 Tushare 小样本验证**
   - 需要 `TUSHARE_TOKEN`；只读少量 code 的 `daily`/`fina_indicator`/`dividend`；
   - 校验字段、单位、限流、PIT `ann_date`。
4. **全市场规模/性能**
   - 5500×20y panel 构建/打开、10k sweep、峰值 RSS；
   - 更新 `docs/performance-baseline.json` 和 `make perf-gate` 门槛。
5. **补齐 C++ ETF/可转债规则与分钟级引擎**
   - 当前只到数据/paper；若要宣传回测语义必须补 C++。
6. **文档一致性**
   - 把 `docs/ARCHITECTURE.md`、`docs/RELEASE.md` 更新到 117/117 的当前状态；
   - 保留限制，不要写 “100% 完成/可实盘”。

---

## 9. 开发/提交工作流

1. 先读 `AGENTS.md`（repo 内工作协议）和本 handoff。
2. 明确改动边界，优先小步：
   - C++ 改动 → 重建扩展 + ctest + 差分 + `make verify-cpp`；
   - Python 改动 → `uv run pytest`、ruff、mypy；
   - UI 改动 → `pnpm -C ui test`、`pnpm -C ui build`、`make e2e`；
   - 桌面改动 → `make desktop-smoke`。
3. 提交：
   ```bash
   cd /Users/fei/Desktop/QuantCore
   git status --short
   git add <明确文件路径>            # 禁止 git add -A / .
   git commit -m "feat(scope): ..."
   git push origin main
   ```
4. push 后看 GitHub Actions：
   ```bash
   gh run list --repo feiiiiii5/QuantCore --limit 3
   gh run view <run-id> --repo feiiiiii5/QuantCore --json jobs \
     --jq '.jobs[] | {name,status,conclusion}'
   ```
5. 文档/功能变化同步 `docs/features.json`、`docs/acceptance-report.md`、
   `docs/PROGRESS.md`、README（不要只改一处）。

---

## 10. 新会话启动提示词（可直接粘贴）

```text
你在 /Users/fei/Desktop/QuantCore 工作。接下来的所有工作只允许在这个仓库内完成，
不要读写/修改 /Users/fei/Desktop/申请季。

先读并遵守：
- /Users/fei/Desktop/QuantCore/AGENTS.md
- /Users/fei/Desktop/QuantCore/docs/HANDOFF.md
- /Users/fei/Desktop/QuantCore/docs/features.json
- /Users/fei/Desktop/QuantCore/docs/acceptance-report.md

当前仓库已知状态：main、public GitHub feiiiiii5/QuantCore、features 117/117（功能门禁）、
CI 5 个 job 全绿、pytest 196 collected/194 passed/2 skipped、ctest 95/95、
Playwright 18/18。不要把“117/117”误解为真实 vendor 实时行情/签名安装包已完成；
已知限制见 HANDOFF 第 7 节。

这是仅研究与模拟的本地工作台：不做真实下单，不接 BrokerGateway，合成数据必须标 SYNTHETIC，
Tushare/AKShare 等网络路径默认关闭/需显式凭据。开始前先跑 git status、git log、
features 计数和最近 CI；改完后跑与改动相关的门禁（至少 make lint + make test；
UI 改动跑 make e2e；C++ 改动跑 make verify-cpp），只 stage 明确路径，按 Conventional Commits
提交并 push，最后报告实际命令/结果与剩余限制。
```

---

## 11. 关键路径速查

| 用途 | 路径/命令 |
|---|---|
| 功能真相源 | `docs/features.json` |
| 验收报告 | `docs/acceptance-report.md` |
| 进度/续跑 | `docs/PROGRESS.md` |
| API 契约 | `docs/UI-API.md` |
| 架构 | `docs/ARCHITECTURE.md` |
| 回测语义 | `docs/engine-semantics.md` |
| 规则来源 | `docs/rules-sources.md` |
| 数据字典 | `docs/data-dictionary.md` |
| 发布/安全 | `docs/RELEASE.md`、`docs/SECURITY.md` |
| C++ 差分/性能 | `make verify-cpp`、`make perf-gate` |
| 本地完整门禁 | `make ci-local` |
| UI E2E | `make e2e`（需要 Chrome） |
| 桌面 smoke | `make desktop-smoke` |
| SBOM/audit | `make sbom`、`make audit` |
| 启动服务 | `uv run qc serve --port 8000 --open` |

---

## 12. 交接结论

QuantCore 当前是一个**可本地运行、可回归、功能门禁 117/117 的 A 股研究与模拟工作台**：
C++20 引擎、Python 控制面、React UI、数据/快照/实验/研究/模拟交易/插件/桌面壳均已接通，
并有 pytest/ctest/Vitest/Playwright/CI/性能门禁证据。

它**不是**实盘交易系统，也**不是**已签名的跨平台安装包；真实 vendor feed、真实 Tushare
网络、Windows 安装运行、全市场规模性能仍是明确的后续工作。新会话请从本文件第 0 节开始，
并保留这些边界，不要把限制性事实改写成完成性声明。
