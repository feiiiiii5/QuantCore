# LOCAL-TESTING — 本地测试与自检总览

> 本项目只做**研究与模拟**：不实现真实下单、不连接券商。默认**全部离线**，测试使用
> SYNTHETIC 合成数据或录制 fixture。历史表现不代表未来，不构成投资建议。

本文汇总本机可用的测试入口、隔离方式与故障排查。安装/镜像见 `DEV-SETUP.md`，
三步跑通见 `QUICKSTART.md`，性能基准与门禁见 `PERFORMANCE.md`。

## 1. 5 分钟冒烟（干净机器）

```bash
make setup       # uv sync + 构建 C++ 扩展 + 前端依赖；首次需要网络/镜像
make demo        # 合成数据 -> 快照 -> 示例回测，一条命令跑通
make test-quick  # 快速回归（排除 e2e / bench / network）
```

- `make setup` 之后 C++ 扩展已构建。`make test-quick` 本身**不构建**扩展；若只 clone
  未 build，请先 `make build`（或 `make setup`），否则依赖 C++ 的用例会 skip。
- `make demo` 输出应包含 `engine_backend: "cpp"` 与净值/指标；数据为 SYNTHETIC。
- 更严格的自检：`make verify-local`（doctor + test-quick，带分段耗时与 PASS/FAIL）；
  提交前的完整门禁 `make ci-local` 由 Lead 统一执行。

## 2. 命令总表

耗时为本机参考（Apple M2 Pro / 16 GB / macOS 27.2，已构建扩展时）；首次运行会慢一些。

| 目标 | 命令 | 耗时 / 前置 | 说明 |
|---|---|---|---|
| 环境自检 | `make doctor` | 约 0.2–2 s；需 uv 环境 | 只读离线检查 Python/.venv、C++ 扩展与 `engine_backend`、数据仓库/快照、前端构建、Node/pnpm、端口、磁盘、Git、Chrome；FAIL 时退出码 1（`uv run qc doctor` 默认 JSON） |
| 一键演示 | `make demo` | 约 2–15 s；无需网络 | SYNTHETIC 面板 → 快照 → 示例回测 → HTML 报告；产物在 `data/demo/` 与 `experiments/<run_id>/`（均 gitignore） |
| 快速回归 | `make test-quick` | 约 30–60 s；不 build | pytest 全量，排除 e2e/bench/network 标记 |
| 本地自检（推荐） | `make verify-local` | 默认约 30–60 s | `bash scripts/local_verify.sh`：doctor + test-quick，分段耗时 + PASS/FAIL，任一失败 exit 1 |
| 本地自检（完整） | `bash scripts/local_verify.sh --full` | 数分钟；会 build | 追加 lint、test（pytest+ctest）、verify-cpp |
| 本地自检（含 UI） | `bash scripts/local_verify.sh --e2e` | 数分钟；需 Chrome | 追加 `make e2e` |
| 单元 + C++ 测试 | `make test` | 数分钟；会先 build | pytest + ctest |
| C++ 验证 | `make verify-cpp` | 数分钟；会先 build | engine_backend=cpp、差分一致、§10 基准 |
| 性能回归门 | `make perf-gate` | 数分钟；会先 build | 对比 `docs/performance-baseline.json` 的本地早预警 |
| Python 基准 | `make bench` | 数分钟；会先 build | `scripts/bench.py` + C++ Google Benchmark |
| 规模基准 | `make bench-scale` | 默认约 5–10 s；无需网络 | 合成面板 → Parquet → .qpanel mmap → engine 单次回测 → 峰值 RSS |
| 端到端 | `make e2e` | 数分钟；需本机 Chrome | 构建 UI + 隔离 qc serve + Playwright |
| 完整门禁 | `make ci-local` | 10+ min | setup + lint + test + verify-cpp + ui-check |
| 单个测试文件 | `uv run pytest tests/test_paper_engine.py -q` | 秒级 | 直接指定文件，调试最快 |
| 关键字过滤 | `uv run pytest -q -k "snapshot and not slow"` | 秒级 | pytest `-k` 表达式 |
| UI 单测 | `pnpm -C ui test` | 数十秒 | vitest |
| UI 构建 | `pnpm -C ui build` | 数十秒 | tsc + vite build；`make e2e` 与 `qc serve` 静态资源需要 |

提示：不确定某个 target 会执行什么时，先用 `make -n <target>` 展开命令（不执行）。

`qc doctor` 默认输出 JSON（`make doctor` 传 `--no-json-output` 输出人类清单）；
`uv run qc doctor --strict` 把 WARN 也视为失败（适合脚本门禁），`--port 0` 关闭端口探测。
`qc demo` 可用 `--n-sec/--start/--end/--seed/--template/--data-root/--experiments-root/--json-output`
调整演示规模与输出。

## 3. 单独跑测试

```bash
# 单个文件 / 单个用例
uv run pytest tests/test_paper_engine.py -q
uv run pytest tests/test_paper_engine.py -q -k "partial_fill"

# 只跑快速集（与 make test-quick 等价）
uv run pytest -q -m "not e2e and not bench and not network"

# 默认被跳过的标记
QC_BENCH=1 uv run pytest -q -m bench            # 性能测试
QC_ALLOW_NETWORK=1 uv run pytest -q -m network  # 网络测试，需凭据；默认不跑
```

pytest 标记（`pyproject.toml`）：`e2e`、`bench`、`network`。`bench` 与
`network` 默认 skip；`e2e` 标记预留给端到端用例（当前 UI e2e 由 Playwright 在
`ui/e2e/` 驱动，`make e2e` 容忍 `pytest -m e2e` 无用例时的 exit 5）。

## 4. UI 与 E2E

```bash
pnpm -C ui install          # 首次
pnpm -C ui test             # vitest 单测
pnpm -C ui build            # 生产构建，供 qc serve / e2e 使用
make e2e                    # UI 构建 + 隔离 qc serve + Playwright
```

- `make e2e` 需要本机安装 **Google Chrome**（`ui/playwright.config.ts` 里
  `channel: "chrome"`）；没有 Chrome 时改用 Playwright 的 Chromium 需先
  `pnpm -C ui exec playwright install chromium` 并调整该配置。
- e2e 使用临时目录与可配置端口（`QC_E2E_PORT`，默认 8123），不会污染真实
  `data/`、`experiments/`。
- e2e **不在 GitHub CI 运行**（需要浏览器/UI 构建），只在本地门禁执行。

## 5. 隔离运行（数据 / 端口 / token）

pytest 用 `tmp_path`，`scripts/e2e.sh` 用 `mktemp`，规模基准用临时目录；
手动起服务时建议同样隔离：

```bash
TMP=$(mktemp -d)
QC_SERVER_TOKEN=local-dev-token uv run qc serve \
  --port 8123 \
  --data-root "$TMP/data" \
  --experiments-root "$TMP/experiments" \
  --no-open
```

另开终端做 API 冒烟（`/health` 公开，`/api/*` 需要 Bearer token）：

```bash
curl -fsS http://127.0.0.1:8123/health
curl -fsS -H "Authorization: Bearer local-dev-token" http://127.0.0.1:8123/api/meta
curl -fsS -H "Authorization: Bearer local-dev-token" http://127.0.0.1:8123/api/doctor
```

常用环境变量：

| 变量 | 作用 |
|---|---|
| `QC_SERVER_TOKEN` | 固定 `qc serve` 的 Bearer token；不设则每次随机生成并打印 |
| `QC_E2E_PORT` | e2e 服务端口，默认 `8123` |
| `QC_E2E_TOKEN` | e2e token，默认 `test-token` |
| `QC_BENCH=1` | 允许运行 `bench` 标记的测试 |
| `QC_ALLOW_NETWORK=1` | 允许 `network` 标记的测试与真实数据源 |
| `UV_DEFAULT_INDEX` / `PIP_INDEX_URL` | 依赖镜像，Makefile 已默认导出（见 `DEV-SETUP.md`） |

清理：`kill` 掉手动启动的 `qc serve`，并删除 `$TMP` 临时目录即可；这些路径不参与
`make ci-local`。

## 6. 规模基准（bench-scale）

```bash
make bench-scale
uv run python scripts/scale_bench.py --n-sec 800 --json     # 默认：800 证券 x 2020-2024
uv run python scripts/scale_bench.py --n-sec 5500 --json    # 全市场规模，需足够内存
```

测量项：合成面板构建、Parquet 写/读、`.qpanel` 写/打开（mmap）、engine 单次回测、
峰值 RSS（`resource.ru_maxrss`，macOS bytes / Linux KiB 已归一化为 MiB）。
本机默认 800 证券实测：约 5–10 s，峰值 RSS 约 1.6 GiB（生成阶段占大头）；全市场
`--n-sec 5500` 建议 ≥16 GiB 空闲内存并预留时间。数字与机器信息见
`PERFORMANCE.md` 的「规模基准」小节。

## 7. 常见故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `engine_backend == "missing"`，大量用例 skip | C++ 扩展未构建/未就绪 | `make build`，再 `uv run python -c "import quantcore; print(quantcore.engine_backend())"` 应输出 `cpp` |
| 页面空白 / API 401 | token 不匹配或服务未启动 | 用启动日志里的 token；访问 `/?token=<token>`；或用 `QC_SERVER_TOKEN` 固定后重启 |
| `Address already in use` | 端口被占用 | `lsof -nP -iTCP:8123 -sTCP:LISTEN` 找到进程并结束，或换 `--port` / `QC_E2E_PORT` |
| 打开页面 404 / 无前端 | UI 未构建 | `pnpm -C ui build`（开发时改用 `pnpm -C ui dev` 代理到后端） |
| `make e2e` 报浏览器缺失 | `channel: "chrome"` 需要本机 Google Chrome | 安装 Chrome；或 `pnpm -C ui exec playwright install chromium` 并临时改用 Chromium |
| `No module named quantcore` / Python 版本不对 | 用了系统 python3（可能是 3.11） | 一律用 `uv run ...`；项目 .venv 是 3.12 |
| bench 用例全部 skip | 默认关闭性能测试 | 需要时 `QC_BENCH=1` |
| network 用例 skip / 数据更新失败 | 默认离线或缺少 Token | 本地测试无需网络；真实数据见第 8 节 |
| 首次 `make setup` 下载慢/超时 | 未走镜像 | 检查 `UV_DEFAULT_INDEX`/`PIP_INDEX_URL`/pnpm registry（`DEV-SETUP.md`） |
| Windows 上脚本不可用 | Windows 安装/脚本未验证 | 优先 macOS/Linux；Windows 见 `DEV-SETUP.md` 的未验证说明 |

## 8. 网络边界与未验证项

- **默认全部离线**：`make test-quick`、`make verify-local`、`make bench-scale`、
  `make e2e` 均不需要网络；测试使用 SYNTHETIC 数据或 fixture。
- 需要网络的场景只有：
  1. 首次 `make setup` / `pnpm -C ui install` 下载依赖（可用镜像）；
  2. 真实 Tushare 数据：设置 `TUSHARE_TOKEN` 且 `QC_ALLOW_NETWORK=1` 后运行
     `qc data update --provider tushare ...`。
- 真实网络路径未在本次验收中跑通（无 Token）；真实数据结果请自行核对质量报告。
- `make e2e` 不在 GitHub CI；Windows 安装未验证；所有演示/基准数据标 `SYNTHETIC`，
  不得当作真实市场结论。

## 9. 相关文档

- `QUICKSTART.md` — 安装、三步跑通、启动工作台
- `DEV-SETUP.md` — 工具链与大陆网络镜像
- `PERFORMANCE.md` — 基准方法、门禁、规模基准实测
- `UI-API.md` / `API.md` — HTTP 契约（含 token 与错误码）
- `AGENTS.md` — 工作协议与完成定义
