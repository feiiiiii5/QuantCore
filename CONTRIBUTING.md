# CONTRIBUTING

1. 先读 `AGENTS.md`、`docs/PLAN.md`、`docs/engine-semantics.md`。
2. M0–M10 记录初始建设；后续围绕真实问题与完整用户流程提交。
3. 验证与风险相称：账本、撮合、收益和数据身份用必要的行为回归，界面检查真实服务；性能改动才需要对应基准。避免重复实现的测试和无收益的防御层。
4. 规则/费率必须附官方来源与核对日期；未核实标 `TODO(verify)`。
5. C++ 核心路径不得回退 Python；Python 纯参考实现只放 `tests/reference`。
6. 单文件 ≤500 行；`make lint test` 全绿；提交信息使用 Conventional Commits。
7. 不引入 GPL/AGPL 运行时依赖；新增依赖需在 `docs/DECISIONS.md` 记录理由与许可证。
8. 不实现真实下单；`BrokerGateway` 默认禁用。
9. 本地快速回归：`make test-quick`（不构建）/ `make verify-local`（doctor + 快速回归）；完整门禁 `make ci-local` 由维护者在提交前统一执行。
