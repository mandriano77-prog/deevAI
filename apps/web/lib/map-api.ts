import type { DecisionRead, RunRead } from "./api";
import type { CoreKpi, DecisionReason, DecisionRow, TrendPoint } from "./mock-data";

export function runToKpi(run: RunRead | null, cpvTarget = 0.5): CoreKpi {
  const cpv = run?.blended_cpv_observed ?? 0;
  const visits = run?.blended_visits ?? 0;
  const spend = run?.blended_spend ?? 0;
  return {
    impressions: 0,
    clicks: 0,
    visits,
    spend,
    ctr: 0,
    cpv,
    cpvTarget: run?.blended_cpv_target ?? cpvTarget,
    reach: 0,
    viewabilityRate: 0,
    winRate: 0,
  };
}

export function runToTrend(run: RunRead | null): TrendPoint[] {
  if (!run?.blended_cpv_observed) return [];
  return [
    {
      weekLabel: run.week_label,
      cpv: run.blended_cpv_observed,
      visits: run.blended_visits ?? 0,
      spend: run.blended_spend ?? 0,
    },
  ];
}

export function toDecisionRow(d: DecisionRead): DecisionRow {
  return {
    id: d.id,
    lineItemId: "",
    module: d.targeting_module,
    key: d.targeting_key,
    value: d.value,
    label: d.field_label ?? d.value,
    previousModifier: d.previous_modifier,
    newModifier: d.new_modifier,
    reason: d.reason as DecisionReason,
    observedCpv: d.observed_cpv,
    observedVisits: d.observed_visits ?? 0,
    observedImpressions: d.observed_impressions ?? 0,
    note: d.note ?? "",
    status: d.status as DecisionRow["status"],
  };
}
