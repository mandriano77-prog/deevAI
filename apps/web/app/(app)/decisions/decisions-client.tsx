"use client";

import { useCallback, useEffect, useState } from "react";

import { DecisionsTable } from "@/components/decisions-table";
import { Topbar } from "@/components/topbar";
import { ApiError, lineItems, runs, type LineItemRead } from "@/lib/api";
import { toDecisionRow } from "@/lib/map-api";
import type { DecisionRow } from "@/lib/mock-data";

export function DecisionsClient() {
  const [rows, setRows] = useState<DecisionRow[]>([]);
  const [items, setItems] = useState<LineItemRead[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [runList, lis] = await Promise.all([
        runs.list({ limit: 1 }),
        lineItems.list(),
      ]);
      setItems(lis);
      const run = runList[0];
      if (!run) {
        setRunId(null);
        setRows([]);
        return;
      }
      setRunId(run.id);
      const decisions = await runs.decisions(run.id);
      setRows(decisions.map(toDecisionRow));
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `Errore API (${e.status})`
          : "Impossibile caricare le decisioni",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleStatusChange = async (
    id: string,
    status: "approved" | "rejected",
  ) => {
    await runs.updateDecision(id, status);
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status } : r)),
    );
  };

  const total = rows.length;
  const boosts = rows.filter((d) => d.newModifier > d.previousModifier).length;
  const cuts = rows.filter(
    (d) => d.newModifier < d.previousModifier && d.newModifier > 0,
  ).length;
  const zeroed = rows.filter((d) => d.newModifier === 0).length;
  const approvedCount = rows.filter((d) => d.status === "approved").length;

  async function handleApply() {
    if (!runId) return;
    setApplying(true);
    setError(null);
    try {
      await runs.apply(runId);
      await load();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `Apply fallito (${e.status})`
          : "Impossibile applicare su DSP",
      );
    } finally {
      setApplying(false);
    }
  }

  return (
    <>
      <Topbar
        title="Decisions"
        subtitle="Proposte settimanali del bidding agent · click per approvare/rigettare"
        lineItems={items}
        onRunComplete={load}
      />

      <main className="space-y-6 p-8">
        {loading ? (
          <p className="text-sm text-ink-400">Caricamento…</p>
        ) : null}

        {error ? (
          <div className="rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        {!loading && !error && rows.length === 0 ? (
          <section className="rounded-lg border border-dashed border-ink-700 bg-ink-900/50 p-8 text-center">
            <h2 className="text-lg font-medium text-ink-50">
              Nessuna decisione ancora
            </h2>
            <p className="mt-2 text-sm text-ink-400">
              Avvia un run dalla dashboard per generare proposte di bid adjustment.
            </p>
          </section>
        ) : null}

        {rows.length > 0 ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-ink-300">
                <span className="font-medium text-ink-50">{total}</span> decisioni —
                <span className="ml-2 text-accent-400">↑ {boosts} boost</span>
                <span className="ml-2 text-red-400">↓ {cuts} cut</span>
                <span className="ml-2 text-red-300">○ {zeroed} azzerato</span>
              </p>
              {approvedCount > 0 ? (
                <button
                  type="button"
                  onClick={() => void handleApply()}
                  disabled={applying}
                  className="rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-ink-50 hover:bg-accent-700 disabled:opacity-50"
                >
                  {applying
                    ? "Applicazione…"
                    : `Applica ${approvedCount} su DSP`}
                </button>
              ) : null}
            </div>

            <DecisionsTable rows={rows} onStatusChange={handleStatusChange} />

            <div className="rounded-md border border-ink-800 bg-ink-900/50 p-4 text-xs text-ink-400">
              <strong className="font-medium text-ink-200">Modalità sicura.</strong>{" "}
              Apply rispetta observation-only (14 giorni) e, finché{" "}
              <code className="text-ink-300">DSP_DRY_RUN=true</code>, logga il payload
              senza scrivere su DV360.
            </div>
          </>
        ) : null}
      </main>
    </>
  );
}
