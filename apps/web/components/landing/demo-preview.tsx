"use client";

import { clsx } from "clsx";

import { CpvTrendChart } from "@/components/cpv-trend-chart";
import { MetricCard } from "@/components/metric-card";
import {
  mockBrand,
  mockBrandTrend,
  mockDecisions,
  mockDigest,
} from "@/lib/mock-data";
import type { DecisionReason } from "@/lib/mock-data";

const reasonLabels: Record<DecisionReason, string> = {
  anomalous_ctr: "click farm",
  over_target: "sopra target",
  under_target: "sotto target",
  on_target: "in target",
  zero_visits: "zero visite",
  low_viewability: "low viewability",
  insufficient_volume: "volume basso",
  exploration_revive: "esplorazione",
};

const demoDecisions = mockDecisions.slice(0, 4);

export function DemoPreview() {
  const kpi = mockBrand.kpi;

  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="text-center">
        <p className="text-xs uppercase tracking-wider text-ink-400">
          Anteprima demo
        </p>
        <h2 className="mt-2 text-2xl font-medium text-ink-50">
          Così si presenta deevAI ogni lunedì
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-ink-300">
          Dati sintetici a scopo illustrativo. Dopo l&apos;accesso vedi le metriche
          reali della tua DSP.
        </p>
      </div>

      <div className="mt-10 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-medium text-ink-50">
              CPV — ultime 8 settimane
            </h3>
            <span className="text-xs text-ink-400">
              target {kpi.cpvTarget.toFixed(2)} €
            </span>
          </div>
          <CpvTrendChart points={mockBrandTrend} target={kpi.cpvTarget} />
        </div>

        <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium text-ink-50">
              Riepilogo del lunedì
            </h3>
            <span className="text-xs text-ink-400">{mockDigest.weekLabel}</span>
          </div>
          <div className="space-y-3 text-sm leading-relaxed text-ink-200">
            {mockDigest.text.split("\n\n").slice(0, 2).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="CPV osservato"
          value={`${kpi.cpv.toFixed(2)} €`}
          hint={`target ${kpi.cpvTarget.toFixed(2)} €`}
          trend="down"
          trendColor="good"
        />
        <MetricCard
          label="Visite"
          value={kpi.visits.toLocaleString("it-IT")}
          trend="up"
          trendColor="good"
        />
        <MetricCard
          label="Spend"
          value={`${kpi.spend.toLocaleString("it-IT", { maximumFractionDigits: 0 })} €`}
          trendColor="neutral"
        />
        <MetricCard
          label="Impressioni"
          value={kpi.impressions.toLocaleString("it-IT")}
          hint={`CTR ${(kpi.ctr * 100).toFixed(2)}%`}
          trendColor="neutral"
        />
      </div>

      <div className="mt-8 overflow-hidden rounded-lg border border-ink-800">
        <div className="border-b border-ink-800 bg-ink-800/50 px-4 py-2 text-xs text-ink-400">
          Decisioni proposte (estratto) · approvazione richiesta prima dell&apos;apply
        </div>
        <table className="w-full text-sm">
          <thead className="bg-ink-800 text-xs uppercase tracking-wider text-ink-400">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Term</th>
              <th className="px-4 py-2 text-left font-medium">Mod.</th>
              <th className="px-4 py-2 text-left font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-800">
            {demoDecisions.map((row) => {
              const delta = row.newModifier - row.previousModifier;
              const arrow = delta > 0 ? "↑" : delta < 0 ? "↓" : "=";
              return (
                <tr key={row.id} className="bg-ink-900">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink-100">
                      {row.label}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    <span className="text-ink-400">
                      {row.previousModifier.toFixed(2)}
                    </span>{" "}
                    <span
                      className={
                        delta > 0 ? "text-accent-400" : "text-red-400"
                      }
                    >
                      {arrow}
                    </span>{" "}
                    <span className="text-ink-50">
                      {row.newModifier.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "inline-block rounded-full border px-2 py-0.5 text-[11px]",
                        row.reason === "anomalous_ctr"
                          ? "border-red-900 bg-red-900/40 text-red-300"
                          : row.reason === "under_target"
                            ? "border-accent-700 bg-accent-900/40 text-accent-400"
                            : "border-red-900/60 bg-red-900/30 text-red-300",
                      )}
                    >
                      {reasonLabels[row.reason]}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
