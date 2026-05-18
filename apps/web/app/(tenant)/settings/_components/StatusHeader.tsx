"use client";

import type { RunRead, SettingRead } from "@/lib/api";
import type { HardConstraintRead } from "@/lib/api/optimization";

interface Props {
  settings: SettingRead;
  constraints: HardConstraintRead[];
  lastRun: RunRead | null;
}

export function StatusHeader({ settings, constraints, lastRun }: Props) {
  const observed = lastRun?.blended_cpv_observed;
  const target = settings.default_cpv_target;
  const delta =
    observed != null && target > 0
      ? ((observed - target) / target) * 100
      : null;

  const observationActive =
    settings.observation_only_until != null &&
    new Date(settings.observation_only_until).getTime() > Date.now();

  return (
    <header className="sticky top-0 z-10 -mx-8 border-b border-ink-800 bg-[#0a0a0a]/95 px-8 py-4 backdrop-blur">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-amber-400" aria-hidden>
            ★
          </span>
          <span className="font-medium text-ink-50">
            CPV {observed != null ? `${observed.toFixed(2)} €` : "—"}
          </span>
          {delta != null ? (
            <span
              className={
                Math.abs(delta) <= settings.tolerance_band * 100
                  ? "text-accent-300"
                  : delta > 0
                    ? "text-red-300"
                    : "text-accent-300"
              }
            >
              {delta > 0 ? "+" : ""}
              {delta.toFixed(0)}% vs target
            </span>
          ) : null}
        </div>
        <span className="rounded-md border border-ink-700 px-2 py-0.5 text-ink-300">
          {constraints.length} constraint attive
        </span>
        <span
          className={
            observationActive
              ? "rounded-md border border-amber-800/60 bg-amber-900/30 px-2 py-0.5 text-amber-100"
              : "rounded-md border border-accent-800/50 bg-accent-900/20 px-2 py-0.5 text-accent-200"
          }
        >
          {observationActive ? "Observation only" : "Attivo"}
        </span>
        {lastRun ? (
          <span className="text-ink-400">
            Ultimo run: {lastRun.week_label} ({lastRun.status})
          </span>
        ) : (
          <span className="text-ink-500">Nessun run ancora</span>
        )}
      </div>
    </header>
  );
}
