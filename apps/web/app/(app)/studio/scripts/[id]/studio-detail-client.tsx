"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  studio,
  type ScriptDetail,
  type SimulationReport,
} from "@/lib/api";

import { SimulationCard } from "../../new/studio-new-client";

/**
 * Single-script view: shows the generated DSL, the slider weights, the
 * latest simulation (if any) and offers a "Re-simulate" + "Archive"
 * action set. The script_source itself is read-only — there is no PATCH
 * endpoint exposed by the API (script content is server-owned).
 */
export function StudioDetailClient({ scriptId }: { scriptId: string }) {
  const router = useRouter();

  const [script, setScript] = useState<ScriptDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [latest, setLatest] = useState<SimulationReport | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await studio.getScript(scriptId);
      setScript(detail);
      setLatest(detail.latestSimulation);
    } catch (e) {
      const msg =
        e instanceof ApiError ? `Errore API (${e.status})` : "Errore di rete";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [scriptId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onResimulate = useCallback(async () => {
    setSimulating(true);
    setSimulationError(null);
    try {
      const report = await studio.simulateScript(scriptId, {});
      setLatest(report);
    } catch (e) {
      const msg =
        e instanceof ApiError ? `Errore API (${e.status})` : "Errore di rete";
      setSimulationError(msg);
    } finally {
      setSimulating(false);
    }
  }, [scriptId]);

  const onArchive = useCallback(async () => {
    if (!confirm("Archiviare questo script? Sarà nascosto dalla lista.")) {
      return;
    }
    setArchiving(true);
    try {
      await studio.archiveScript(scriptId);
      router.push("/studio");
    } catch (e) {
      const msg =
        e instanceof ApiError ? `Errore API (${e.status})` : "Errore di rete";
      setError(msg);
      setArchiving(false);
    }
  }, [scriptId, router]);

  if (loading) {
    return <div className="p-8 text-sm text-ink-400">Carico…</div>;
  }
  if (error) {
    return <div className="p-8 text-sm text-rose-400">{error}</div>;
  }
  if (!script) {
    return <div className="p-8 text-sm text-ink-400">Script non trovato.</div>;
  }

  return (
    <div className="p-8">
      <header className="mb-6 flex items-start justify-between">
        <div>
          <Link
            href="/studio"
            className="text-xs text-ink-400 hover:text-ink-200"
          >
            ← Studio
          </Link>
          <h1 className="mt-1 text-2xl font-semibold text-ink-50">
            {script.name}
          </h1>
          <div className="mt-2 flex items-center gap-3 text-xs">
            <StatusBadge status={script.status} />
            <span className="font-mono text-ink-400">
              sha {script.scriptSha256.slice(0, 16)}
            </span>
            <span className="text-ink-400">
              {script.sizeBytes} bytes ·{" "}
              {new Date(script.createdAt).toLocaleString()}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onResimulate}
            disabled={simulating || script.status === "archived"}
            className="rounded-md bg-ink-800 px-3 py-1.5 text-xs text-ink-50 hover:bg-ink-600 disabled:opacity-50"
          >
            {simulating ? "Simulo…" : "Re-simula"}
          </button>
          <button
            onClick={onArchive}
            disabled={archiving || script.status === "archived"}
            className="rounded-md border border-ink-800 px-3 py-1.5 text-xs text-ink-200 hover:bg-ink-800 disabled:opacity-50"
          >
            {script.status === "archived" ? "Archiviato" : "Archivia"}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Weights */}
        <section className="rounded-lg border border-ink-800 bg-ink-900 p-4">
          <h2 className="mb-2 text-sm font-semibold text-ink-50">Pesi</h2>
          <dl className="grid grid-cols-3 gap-3 text-center text-xs">
            <WeightCell
              label="Performance"
              value={script.weights.performance}
            />
            <WeightCell label="Quality" value={script.weights.quality} />
            <WeightCell label="Reach" value={script.weights.reach} />
          </dl>
        </section>

        {/* Latest simulation */}
        <section className="rounded-lg border border-ink-800 bg-ink-900 p-4">
          <h2 className="mb-2 text-sm font-semibold text-ink-50">
            Ultima simulazione
          </h2>
          {simulationError && (
            <p className="text-xs text-rose-400">{simulationError}</p>
          )}
          {!latest ? (
            <p className="text-xs text-ink-400">
              Nessuna simulazione eseguita. Premi <strong>Re-simula</strong>.
            </p>
          ) : (
            <SimulationCard report={latest} />
          )}
        </section>
      </div>

      {/* Source */}
      <section className="mt-6 rounded-lg border border-ink-800 bg-ink-900 p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-50">Script DSL</h2>
          <span className="text-xs text-ink-400">
            Read-only — generato dal server.
          </span>
        </div>
        <pre className="overflow-x-auto rounded-md bg-ink-900 p-3 font-mono text-[11px] leading-relaxed text-ink-200">
          {script.scriptSource}
        </pre>
      </section>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    draft: "bg-ink-800 text-ink-200",
    simulated: "bg-accent-900 text-accent-100",
    uploaded: "bg-blue-900 text-blue-100",
    active: "bg-green-900 text-green-100",
    archived: "bg-ink-800 text-ink-400 line-through",
  };
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs ${
        styles[status] ?? "bg-ink-800 text-ink-200"
      }`}
    >
      {status}
    </span>
  );
}

function WeightCell({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-ink-800 px-2 py-3">
      <div className="text-ink-400">{label}</div>
      <div className="text-lg font-semibold text-ink-50">{value}</div>
    </div>
  );
}
