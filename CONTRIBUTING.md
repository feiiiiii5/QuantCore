# CONTRIBUTING

1. 先读 `AGENTS.md`、`docs/PLAN.md`、`docs/engine-semantics.md`。
2. 按里程碑与门禁推进；门禁不过不合并。
3. 测试先行：单元/属性/黄金/差分/确定性/未来函数按 `docs/PLAN.md` §11 要求。
4. 规则/费率必须附官方来源与核对日期；未核实标 `TODO(verify)`。
5. C++ 核心路径不得回退 Python；Python 纯参考实现只放 `tests/reference`。
6. 单文件 ≤500 行；`make lint test` 全绿；提交信息使用 Conventional Commits。
7. 不引入 GPL/AGPL 运行时依赖；新增依赖需在 `docs/DECISIONS.md` 记录理由与许可证。
8. 不实现真实下单；`BrokerGateway` 默认禁用。
