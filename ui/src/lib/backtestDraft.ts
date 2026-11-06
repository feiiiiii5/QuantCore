import type { ExperimentDetail } from "../api/types";
import type { BacktestDraft } from "../store/workspace";
import { dateInt } from "./format";

type Values = Record<string, unknown>;
const record = (value: unknown): Values => value && typeof value === "object" ? value as Values : {};

export function restoreDraft(detail: ExperimentDetail, defaults: BacktestDraft): BacktestDraft {
  const strategy = record(detail.metadata.strategy);
  if (typeof strategy.template !== "string") throw new Error("本页只支持模板策略；自定义插件请在策略页运行。");
  const config = record(detail.metadata.config);
  const costs = record(config.costs), exec = record(config.exec), risk = record(config.risk);
  const result = detail.result;
  const text = (value: unknown, fallback: string) => value == null ? fallback : String(value);
  const date = (value: unknown) => dateInt(typeof value === "number" || typeof value === "string" ? value : undefined);
  const rate = (value: unknown, fallback: string) => typeof value === "number" ? String(value * 100) : fallback;
  const params = { ...record(strategy.params), ...(strategy.rebalance != null ? { rebalance: strategy.rebalance } : {}) };
  return {
    ...defaults, template: strategy.template, paramsText: JSON.stringify(params),
    start: date(config.start ?? result?.dates[0]), end: date(config.end ?? result?.dates.at(-1)),
    cash: text(config.initial_cash, defaults.cash), trace: text(config.trace, defaults.trace), seed: text(config.seed, defaults.seed),
    benchmarkCode: text(config.benchmark_code, ""), exec: text(exec.type, defaults.exec),
    commissionRate: rate(costs.commission_rate, defaults.commissionRate), minCommission: text(costs.min_commission, defaults.minCommission),
    stampDutyRate: rate(costs.stamp_duty_rate, defaults.stampDutyRate), slippageBps: text(exec.slippage_bps, defaults.slippageBps),
    maxParticipation: text(exec.max_participation, defaults.maxParticipation), minRebalanceValue: text(exec.min_rebalance_value, defaults.minRebalanceValue),
    maxPositions: text(risk.max_positions, ""), maxWeight: text(risk.max_weight, ""),
  };
}

export function configFromDraft(draft: BacktestDraft, detail?: ExperimentDetail): Values {
  const config = record(detail?.metadata.config);
  return {
    ...config, start: draft.start, end: draft.end, initial_cash: Number(draft.cash), trace: draft.trace, seed: Number(draft.seed),
    benchmark_code: draft.benchmarkCode.trim() || null,
    costs: {
      ...record(config.costs), commission_rate: Number(draft.commissionRate) / 100,
      min_commission: Number(draft.minCommission), stamp_duty_rate: Number(draft.stampDutyRate) / 100,
    },
    exec: {
      ...record(config.exec), type: draft.exec, slippage_bps: Number(draft.slippageBps),
      max_participation: Number(draft.maxParticipation), min_rebalance_value: Number(draft.minRebalanceValue),
    },
    risk: {
      ...record(config.risk), max_positions: draft.maxPositions ? Number(draft.maxPositions) : null,
      max_weight: draft.maxWeight ? Number(draft.maxWeight) : null,
    },
  };
}
