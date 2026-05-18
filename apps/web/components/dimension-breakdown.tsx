/**
 * Breakdown panels for the Line Item view.
 *
 * Five panels:
 *   - Domains (top by spend)
 *   - Apps
 *   - Devices (4 device types)
 *   - Regions (Italian regions, top 10)
 *   - Audiences (audience segments)
 *
 * Plus a Daypart heatmap (24×7) showing CPV intensity by hour × day.
 * Each row shows the current bid modifier — that's where you see
 * "this term is currently boosted/cut and by how much".
 */

import { clsx } from "clsx";

import type { DaypartCell, DimensionRow } from "@/lib/mock-data";

const dayLabels = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

interface DimensionTableProps {
  title: string;
  description?: string;
  rows: DimensionRow[];
  cpvTarget: number;
  limit?: number;
}

export function DimensionTable({
  title,
  description,
  rows,
  cpvTarget,
  limit = 5,
}: DimensionTableProps) {
  const visibleRows = rows.slice(0, limit);

  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-ink-50">{title}</h3>
        {description ? (
          <span className="text-xs text-ink-400">{description}</span>
        ) : null}
      </div>
      <table className="w-full text-xs">
        <thead className="text-ink-400">
          <tr className="border-b border-ink-800">
            <th className="py-2 text-left font-normal">Termine</th>
            <th className="py-2 text-right font-normal">CPV</th>
            <th className="py-2 text-right font-normal">Visite</th>
            <th className="py-2 text-right font-normal">Spend</th>
            <th className="py-2 text-right font-normal">Mod.</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-800">
          {visibleRows.map((row) => {
            const ratio = row.cpv / cpvTarget;
            const cpvColor =
              ratio > 1.5
                ? "text-red-400"
                : ratio < 0.8
                ? "text-accent-400"
                : "text-ink-200";

            const modifierColor =
              row.modifier > 1.05
                ? "text-accent-400"
                : row.modifier < 0.95
                ? "text-red-400"
                : "text-ink-400";

            return (
              <tr key={row.value}>
                <td className="py-2 text-ink-100">{row.label}</td>
                <td className={clsx("py-2 text-right font-mono", cpvColor)}>
                  {row.cpv.toFixed(2)} €
                </td>
                <td className="py-2 text-right text-ink-300">
                  {row.visits.toLocaleString("it-IT")}
                </td>
                <td className="py-2 text-right text-ink-300">
                  {row.spend.toLocaleString("it-IT", {
                    maximumFractionDigits: 0,
                  })} €
                </td>
                <td className={clsx("py-2 text-right font-mono", modifierColor)}>
                  {row.modifier.toFixed(2)}×
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length > limit ? (
        <div className="mt-2 text-right text-xs text-ink-500">
          +{rows.length - limit} altri
        </div>
      ) : null}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// Daypart heatmap (24×7)
// ────────────────────────────────────────────────────────────────

interface DaypartHeatmapProps {
  cells: DaypartCell[];
  cpvTarget: number;
}

export function DaypartHeatmap({ cells, cpvTarget }: DaypartHeatmapProps) {
  // Color scale: cpv ratio → bg color
  // ratio < 1.0 → green-ish (cheap visits) | ratio > 1.0 → red-ish (expensive)
  // visits == 0 → ink (no data)
  const cellFor = (day: number, hour: number) =>
    cells.find((c) => c.day === day && c.hour === hour);

  function colorFor(cell: DaypartCell): string {
    if (cell.visits === 0) return "#1a1a18";
    const ratio = cell.cpv / cpvTarget;
    if (ratio < 0.5) return "#0e6049"; // deep accent — very cheap
    if (ratio < 0.8) return "#178060";
    if (ratio < 1.2) return "#3aa882"; // on target
    if (ratio < 2) return "#7a3a3a"; // mildly over
    return "#a13838"; // very over
  }

  return (
    <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-ink-50">Daypart heatmap</h3>
        <span className="text-xs text-ink-400">CPV per ora × giorno</span>
      </div>

      <div className="overflow-x-auto">
        <table className="text-[10px]">
          <thead>
            <tr>
              <th className="px-1 text-left font-normal text-ink-400"></th>
              {Array.from({ length: 24 }).map((_, h) => (
                <th
                  key={h}
                  className="px-0.5 text-center font-normal text-ink-400"
                >
                  {h % 3 === 0 ? h : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dayLabels.map((dayLabel, dayIdx) => (
              <tr key={dayLabel}>
                <td className="pr-2 text-ink-400">{dayLabel}</td>
                {Array.from({ length: 24 }).map((_, h) => {
                  const cell = cellFor(dayIdx, h);
                  if (!cell) return <td key={h}></td>;
                  const bg = colorFor(cell);
                  return (
                    <td
                      key={h}
                      title={`${dayLabel} ${h}:00 — ${cell.visits} visite, CPV ${cell.cpv.toFixed(2)} €`}
                      className="w-3 h-4 cursor-default"
                      style={{ backgroundColor: bg }}
                    />
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-400">
        <span>Cheap</span>
        <div className="flex h-3 w-32 overflow-hidden rounded">
          <div className="flex-1" style={{ background: "#0e6049" }} />
          <div className="flex-1" style={{ background: "#178060" }} />
          <div className="flex-1" style={{ background: "#3aa882" }} />
          <div className="flex-1" style={{ background: "#7a3a3a" }} />
          <div className="flex-1" style={{ background: "#a13838" }} />
        </div>
        <span>Expensive</span>
      </div>
    </div>
  );
}
