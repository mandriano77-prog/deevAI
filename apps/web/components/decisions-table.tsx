"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";

import type { DecisionReason, DecisionRow } from "@/lib/mock-data";

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

const reasonStyles: Record<DecisionReason, string> = {
  anomalous_ctr: "bg-red-900/40 text-red-300 border-red-900",
  over_target: "bg-red-900/30 text-red-300 border-red-900/60",
  under_target: "bg-accent-900/40 text-accent-400 border-accent-700",
  on_target: "bg-ink-800 text-ink-200 border-ink-700",
  zero_visits: "bg-red-900/40 text-red-300 border-red-900",
  low_viewability: "bg-amber-900/40 text-amber-300 border-amber-900",
  insufficient_volume: "bg-ink-800 text-ink-300 border-ink-700",
  exploration_revive: "bg-amber-900/40 text-amber-300 border-amber-900",
};

interface DecisionsTableProps {
  rows: DecisionRow[];
  onStatusChange?: (
    id: string,
    status: "approved" | "rejected",
  ) => Promise<void>;
}

export function DecisionsTable({ rows, onStatusChange }: DecisionsTableProps) {
  const [local, setLocal] = useState(rows);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    setLocal(rows);
  }, [rows]);

  const setStatus = async (
    id: string,
    newStatus: "approved" | "rejected",
  ) => {
    setBusyId(id);
    try {
      if (onStatusChange) {
        await onStatusChange(id, newStatus);
      }
      setLocal((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: newStatus } : r)),
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="overflow-hidden rounded-lg border border-ink-800">
      <table className="w-full text-sm">
        <thead className="bg-ink-800 text-xs uppercase tracking-wider text-ink-400">
          <tr>
            <th className="px-4 py-2 text-left font-medium">Term</th>
            <th className="px-4 py-2 text-left font-medium">CPV</th>
            <th className="px-4 py-2 text-left font-medium">Mod.</th>
            <th className="px-4 py-2 text-left font-medium">Reason</th>
            <th className="px-4 py-2 text-right font-medium">Azioni</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-800">
          {local.map((row) => {
            const delta = row.newModifier - row.previousModifier;
            const arrow = delta > 0 ? "↑" : delta < 0 ? "↓" : "=";
            const arrowColor =
              delta > 0
                ? "text-accent-400"
                : delta < 0
                ? "text-red-400"
                : "text-ink-400";

            return (
              <tr key={row.id} className="bg-ink-900">
                <td className="px-4 py-3 align-top">
                  <div className="font-medium text-ink-100">{row.label}</div>
                  <div className="text-xs text-ink-400">
                    {row.module}.{row.key}
                  </div>
                </td>
                <td className="px-4 py-3 align-top text-ink-200">
                  {row.observedCpv !== null
                    ? `${row.observedCpv.toFixed(2)} €`
                    : "—"}
                  <div className="text-xs text-ink-400">
                    {row.observedVisits.toLocaleString("it-IT")} visite
                  </div>
                </td>
                <td className="px-4 py-3 align-top font-mono text-xs">
                  <span className="text-ink-400">
                    {row.previousModifier.toFixed(2)}
                  </span>{" "}
                  <span className={arrowColor}>{arrow}</span>{" "}
                  <span className="font-medium text-ink-50">
                    {row.newModifier.toFixed(2)}
                  </span>
                </td>
                <td className="px-4 py-3 align-top">
                  <span
                    className={clsx(
                      "inline-block rounded-full border px-2 py-0.5 text-[11px]",
                      reasonStyles[row.reason],
                    )}
                  >
                    {reasonLabels[row.reason]}
                  </span>
                  <div className="mt-1 max-w-md text-xs text-ink-400">
                    {row.note}
                  </div>
                </td>
                <td className="px-4 py-3 align-top text-right">
                  {row.status === "proposed" ? (
                    <div className="flex justify-end gap-2">
                      <button
                        disabled={busyId === row.id}
                        onClick={() => void setStatus(row.id, "rejected")}
                        className="rounded border border-ink-700 px-2 py-1 text-xs text-ink-300 hover:border-red-700 hover:text-red-300 disabled:opacity-50"
                      >
                        Rigetta
                      </button>
                      <button
                        disabled={busyId === row.id}
                        onClick={() => void setStatus(row.id, "approved")}
                        className="rounded bg-accent-700 px-2 py-1 text-xs font-medium text-ink-50 hover:bg-accent-600 disabled:opacity-50"
                      >
                        Approva
                      </button>
                    </div>
                  ) : (
                    <span
                      className={clsx(
                        "text-xs",
                        row.status === "approved" && "text-accent-400",
                        row.status === "rejected" && "text-red-400",
                        row.status === "applied" && "text-ink-200",
                      )}
                    >
                      {row.status === "approved" && "✓ approvata"}
                      {row.status === "rejected" && "✗ rigettata"}
                      {row.status === "applied" && "applicata"}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
