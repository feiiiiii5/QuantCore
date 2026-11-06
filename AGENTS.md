# AGENTS.md — QuantCore

本地 A 股量化研究与回测工作台。目标：行情→选股→策略→回测→复盘→模拟交易→实验复现，
C++20 核心 `qcore`，Python 控制面，React UI，本地优先、零云依赖、仅研究与模拟。

## 工作协议
- M0–M10 是初始建设记录；后续优化按真实问题与完整用户流程组织，提交使用 Conventional Commits。
- 验证按改动风险取舍：账本、撮合、收益口径与数据身份需要行为回归；界面用真实服务检查。避免与实现重复的测试，不为低影响改动建立额外基础设施；不留空桩、不拿 mock 冒充集成。
- 所有规则/费率/接口字段未经官方来源核实的，标 `TODO(verify)` 并记入 `docs/rules-sources.md`。
- 演示数据只能使用标注 `SYNTHETIC` 的合成数据；禁止把合成结果写成真实市场结论。
- 网络层只用录制 fixture 测试；Tushare Token 等凭据缺失时用 Synthetic + fixture 完成开发。
- 大陆网络：pip/uv 用清华镜像，npm 用 npmmirror，Homebrew 用中科大/清华镜像；见 `docs/DEV-SETUP.md`。
- 单文件 ≤500 行；路由/模块按领域拆分。
- 性能关键路径必须走 C++；Python 纯实现只允许在 `tests/reference/`。
- 引擎性能优化需有相关基准、差分与确定性证据；其他改动按实际影响验证。发布构建禁用 `-march=native`。
- 不实现真实下单；`BrokerGateway` 默认禁用；UI/报告标注“历史表现不代表未来，不构成投资建议”。

## 命令
```bash
make setup        # uv sync + 构建扩展 + 前端依赖（可选）
make build        # 构建 C++ / Python 扩展
make test         # pytest + ctest
make bench        # C++/Python 基准
make lint         # ruff + mypy + clang-format
make verify-cpp   # engine_backend=cpp, 差分一致, §10 基准达标
make e2e          # Playwright（M6 后）
make ci-local     # 本地完整门禁
make package      # wheel + UI 构建
```

## 目录
- `cpp/`：qcore C++20；`cpp/include/qcore` 公共头，`cpp/src/{core,panel,kernels,sim,analytics,sweep,bindings}`，`cpp/tests`，`cpp/bench`，`cpp/fuzz`。
- `python/quantcore/`：data/providers/ingest/quality/snapshot/strategy/research/experiments/server/jobs/cli/report。
- `tests/{reference,golden}`：纯 Python 参考实现与黄金用例。
- `ui/`：TypeScript + React 19 + Vite；`desktop/`：Electron（M10）。
- `docs/`：PLAN/PROGRESS/DECISIONS/engine-semantics/rules-sources/data-dictionary/API 等。

## 完成定义（全量）
features.json 全 passes=true；`make ci-local`、`make verify-cpp`、`make e2e` 全绿；干净机器三步跑通合成回测；
真实 Tushare 数据跑通一次（无 Token 注明未验证项）；文档齐全；验收报告逐条对照提示词。
