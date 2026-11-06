# Sites 私有测试入口

QuantCore 的主要形态是浏览器工作台：React 网页连接本机 FastAPI 与 C++20 引擎；Electron 是额外的客户端壳。普通 `qc serve` 同时提供页面和 API，打开 `http://127.0.0.1:8000` 即可使用。

私有入口：[QuantCore 本地量化工作台](https://quantcore-workbench.blithe-basil-5127.chatgpt.site)。Site 托管实际前端，Python/C++、数据、实验和虚拟账户仍在访问者自己的电脑运行。另一台设备打开 Site 时，`127.0.0.1` 指向那台设备，不能借此访问原电脑。

## 连接本机

在已安装的 QuantCore 项目目录启动：

```bash
QC_ALLOW_NETWORK=1 uv run --frozen qc serve --port 8000 \
  --allow-origin https://quantcore-workbench.blithe-basil-5127.chatgpt.site
```

打开 Site，首次使用会进入设置。API 地址已预填 `http://127.0.0.1:8000`；填写启动时输出的 Token，测试连接并保存。Token 只发往配置的 API；不要把它提交到仓库。只在需要网络行情时设置 `QC_ALLOW_NETWORK=1`。

需要登录私有 Site。浏览器也可能要求允许该网页访问本机网络；是否允许由用户在浏览器中决定。关闭本地服务后，Site 页面仍可打开，计算、行情与账户 API 会离线。

## 边界与证据

- 已发布私有前端，未部署云端 Python/C++ 后端，也没有公开本机端口。
- 默认仍关闭跨域。`--allow-origin` 只接受明确 HTTPS origin；本机 Host、Bearer 及 WebSocket 检查保持有效，预检支持 PNA。
- 桥接回归验证了正常/拒绝预检、实际鉴权、Host/Origin 和 WebSocket。Sites 原生部署结果确认发布成功。
- 已登录真实浏览器从 Site 连接本机的完整验收尚未完成：IAB 控制连接失败，原生浏览器又报告用户切换窗口，自动操作已停止。不能把部署成功等同于该浏览器链路已验证。

## 更新前端

Site 身份保存在 `.openai/hosting.json`，更新时复用同一项目。执行 `python scripts/export_site_frontend.py`，在 `.sites/quantcore` 生成静态资源和对应前端源代码；其中不含本机数据和 Token。

再按 Sites 插件的 source workflow 推送该导出目录、打包并发布到原 Site。发布凭据只通过隐藏 stdin 传递；不要把 Sites source workflow 在 QuantCore GitHub 检出根目录运行。Site 与 GitHub 各自的源码提交不能混为同一个 SHA。
