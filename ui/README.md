# QuantCore UI

TypeScript + React 19 + Vite。分析图 ECharts；K 线 lightweight-charts（Apache-2.0，TradingView）；
策略编辑 Monaco；表格 TanStack Table（后续接虚拟滚动）；i18n zh-CN；系统字体栈；浅/深主题与密度由
`data-theme`/`data-density` 切换。运行期只连本地 `qc serve`（127.0.0.1），Bearer Token 存本机
localStorage，不引入 CDN/远程字体。

## ADR：K 线库
- 选用 **lightweight-charts**：Apache-2.0、包体积小、性能好、5.x 支持 panes/自定义系列；画线能力通过
  自绘覆盖层补足（M6 后续）。KLineChart 作为备选（画线更全，但需再核许可证与包体积）。
- 分析图用 ECharts（Apache-2.0）；策略编辑 Monaco（MIT）；表格 TanStack Table（MIT）。

## 常用命令
```bash
pnpm install
pnpm dev      # http://127.0.0.1:5173
pnpm build
pnpm test
```
后端未启动时页面显示“未连接本地服务”；在“设置”里填入 `qc serve` 打印的地址与 Token。
