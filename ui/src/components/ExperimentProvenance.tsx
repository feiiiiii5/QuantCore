import type { BacktestResultPayload, ExperimentMetadata } from "../api/types";
import { Link } from "react-router-dom";
import { comparisonValue } from "../lib/experimentComparison";
import { dateInt, money } from "../lib/format";
import { Badge } from "./index";

export default function ExperimentProvenance({ metadata, result }: { metadata: ExperimentMetadata; result?: BacktestResultPayload | null }) {
  const config = result?.config ?? metadata.config ?? {};
  const snapshot = result?.snapshot ?? metadata.snapshot;
  const source = snapshot?.source || "未记录";
  const synthetic = result?.synthetic ?? metadata.synthetic ?? snapshot?.synthetic;
  return (
    <details className="exp-provenance">
      <summary><span>数据与运行记录</span><Badge tone={synthetic ? "info" : "neutral"}>{synthetic ? "SYNTHETIC" : source}</Badge></summary>
      <dl className="exp-source-list exp-provenance-grid">
        <div><dt>实际区间</dt><dd>{dateInt(result?.dates[0])} → {dateInt(result?.dates.at(-1))}</dd></div>
        <div><dt>初始资金</dt><dd>{money(typeof config.initial_cash === "number" ? config.initial_cash : null)}</dd></div>
        <div><dt>数据快照</dt><dd className="mono">{snapshot?.snapshot_id || "未绑定快照"}</dd></div>
        <div><dt>数据指纹</dt><dd className="mono">{snapshot?.content_hash || "未记录"}</dd></div>
        <div><dt>数据来源</dt><dd>{source}{synthetic === true ? " · SYNTHETIC" : ""}</dd></div>
        <div><dt>引擎</dt><dd>{result?.engine_backend || metadata.engine_backend || "未记录"} {result?.engine_version || metadata.engine_version}</dd></div>
        <div><dt>策略指纹</dt><dd className="mono">{metadata.strategy_hash || "未记录"}</dd></div>
        <div><dt>代码版本</dt><dd className="mono">{metadata.environment?.git_commit || "未记录"}</dd></div>
        {metadata.parent_run_id ? <div><dt>来源实验</dt><dd><Link to={`/experiments?run=${encodeURIComponent(metadata.parent_run_id)}`}>{metadata.parent_run_id}</Link></dd></div> : null}
      </dl>
      <div className="exp-provenance-grid">
        <div><h4>策略参数</h4><pre className="exp-value">{comparisonValue(metadata.strategy?.params)}</pre></div>
        <div><h4>费用</h4><pre className="exp-value">{comparisonValue(config.costs)}</pre></div>
        <div><h4>成交条件</h4><pre className="exp-value">{comparisonValue(config.exec)}</pre></div>
        <div><h4>风险限制</h4><pre className="exp-value">{comparisonValue(config.risk)}</pre></div>
      </div>
      <p className="page-note-sm">记录来自该次实验，当前工作台切换数据或修改参数不会改变这里的历史记录。</p>
    </details>
  );
}
