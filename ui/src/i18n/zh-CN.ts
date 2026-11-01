export const zhCN = {
  appName: "QuantCore",
  tagline: "本地 A 股量化研究与回测工作台",
  disclaimer: "历史表现不代表未来，不构成投资建议。",
  nav: {
    market: "行情",
    screener: "选股",
    strategy: "策略",
    backtest: "回测",
    experiments: "实验",
    data: "数据",
    settings: "设置",
  },
  status: {
    dataDate: "数据截止",
    source: "数据源",
    task: "任务",
    network: "网络",
    disconnected: "未连接本地服务",
  },
  common: {
    empty: "暂无数据",
    loading: "加载中…",
    connectHint: "请先启动 qc serve，然后在设置中填入地址与 Token。",
    retry: "重试",
    save: "保存",
    run: "运行",
    cancel: "取消",
  },
};
export type Messages = typeof zhCN;
