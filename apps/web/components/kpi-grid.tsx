/**
 * Reusable KPI grid. Takes the bidagent CoreKpi + deltas and renders
 * a responsive grid of MetricCards.
 *
 * Use it on Brand, Campaign and LineItem pages — same component, same
 * data shape, different scope.
 */

import type { CoreKpi, KpiDelta } from "@/lib/mock-data";
import { MetricCard } from "./metric-card";

interface KpiGridProps {
  kpi: CoreKpi;
  delta?: KpiDelta;
  budgetTotal?: number;
  showTier2?: boolean;
}

function fmtEur(n: number, fractionDigits = 2): string {
  return n.toLocaleString("it-IT", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

function fmtInt(n: number): string {
  return n.toLocaleString("it-IT");
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function deltaHint(delta: number | undefined, isGoodWhenNeg = false): {
  hint: string;
  trend: "up" | "down" | "neutral";
  color: "good" | "bad" | "neutral";
} | null {
  if (delta === undefined || delta === 0) return null;
  const pct = Math.round(delta * 100);
  const sign = pct > 0 ? "+" : "";
  const isImprovement = isGoodWhenNeg ? delta < 0 : delta > 0;
  return {
    hint: `${sign}${pct}% vs settimana scorsa`,
    trend: delta > 0 ? "up" : "down",
    color: isImprovement ? "good" : "bad",
  };
}

export function KpiGrid({ kpi, delta, budgetTotal, showTier2 = true }: KpiGridProps) {
  const cpvDelta = deltaHint(delta?.cpvDeltaPct, true); // CPV ↓ is good
  const visitsDelta = deltaHint(delta?.visitsDeltaPct);
  const spendDelta = deltaHint(delta?.spendDeltaPct);
  const reachDelta = deltaHint(delta?.reachDeltaPct);

  return (
    <div className="space-y-3">
      {/* Tier 1 — must-have */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="CPV osservato"
          value={`${fmtEur(kpi.cpv)} €`}
          hint={cpvDelta?.hint ?? `target ${fmtEur(kpi.cpvTarget)} €`}
          trend={cpvDelta?.trend}
          trendColor={cpvDelta?.color}
        />
        <MetricCard
          label="Visite"
          value={fmtInt(kpi.visits)}
          hint={visitsDelta?.hint}
          trend={visitsDelta?.trend}
          trendColor={visitsDelta?.color}
        />
        <MetricCard
          label="Spend"
          value={`${fmtEur(kpi.spend, 0)} €`}
          hint={
            budgetTotal
              ? `su ${fmtEur(budgetTotal, 0)} € budget`
              : spendDelta?.hint
          }
          trend={spendDelta?.trend}
          trendColor="neutral"
        />
        <MetricCard
          label="Impressioni"
          value={fmtInt(kpi.impressions)}
          hint={`CTR ${fmtPct(kpi.ctr)}`}
          trendColor="neutral"
        />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Reach unique"
          value={fmtInt(kpi.reach)}
          hint={reachDelta?.hint ?? "utenti distinti"}
          trend={reachDelta?.trend}
          trendColor={reachDelta?.color}
        />
        <MetricCard
          label="Viewability"
          value={fmtPct(kpi.viewabilityRate)}
          hint="quota impression viewable"
          trendColor="neutral"
        />
        <MetricCard
          label="Win rate"
          value={fmtPct(kpi.winRate)}
          hint="bid vinti / tentati"
          trendColor="neutral"
        />
        {showTier2 && kpi.frequency ? (
          <MetricCard
            label="Frequenza"
            value={kpi.frequency.toFixed(2)}
            hint="impressioni per utente"
            trendColor="neutral"
          />
        ) : (
          <MetricCard
            label="—"
            value="—"
            hint=""
            trendColor="neutral"
          />
        )}
      </div>

      {/* Tier 2 — conversions / ROAS / NTB (when present) */}
      {showTier2 && (kpi.conversions || kpi.roas || kpi.ntbConversions) ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {kpi.conversions !== undefined ? (
            <MetricCard
              label="Conversioni"
              value={fmtInt(kpi.conversions)}
              hint="eventi post-visita attribuiti"
              trendColor="neutral"
            />
          ) : null}
          {kpi.roas !== undefined ? (
            <MetricCard
              label="ROAS"
              value={`${kpi.roas.toFixed(2)}×`}
              hint="ricavi / spend"
              trendColor={kpi.roas >= 2 ? "good" : "neutral"}
            />
          ) : null}
          {kpi.ntbConversions !== undefined ? (
            <MetricCard
              label="New-to-brand"
              value={fmtInt(kpi.ntbConversions)}
              hint="conversioni da utenti mai esposti"
              trendColor="neutral"
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
