# SECURITY — 本地服务与桌面安全

- 服务只绑定 `127.0.0.1`，随机端口，每次启动随机 Bearer Token；校验 Host/Origin；禁止通配 CORS。
- Electron（M10）：`contextIsolation: true`、`sandbox: true`、`nodeIntegration: false`、严格 CSP、仅本地资源。
- 凭据入系统钥匙串（keyring/Keychain/Credential Manager）；日志脱敏；数据源 Token 不写入仓库/实验产物。
- 策略在独立 worker 子进程运行：超时、内存上限、默认禁网、禁止写工作区外路径（Python 审计钩子）；导入他人策略需显式确认。
- 不做真实下单；`BrokerGateway` 默认禁用且需显式启用 + 二次确认（M9）。
- 依赖锁定与审计：pip-audit / npm audit / 许可证检查 / SBOM（M10）；默认无遥测；更新包签名校验。
- 脱敏诊断包导出；崩溃报告不含持仓/凭据/用户路径。
