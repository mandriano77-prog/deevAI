"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, studio, type ScriptRead } from "@/lib/api";

/**
 * Studio landing — table of scripts in the current tenant plus a CTA to
 * launch the slider wizard. Archived rows are excluded by default; the
 * "include archived" toggle hits the same endpoint with status=archived.
 */
export function StudioListClient() {
  const [scripts, setScripts] = useState<ScriptRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await studio.listScripts(
        includeArchived ? { status: "archived" } : undefined,
      );
      setScripts(list);
    } catch (e) {
      const msg =
        e instanceof ApiError ? `Errore API (${e.status})` : "Errore di rete";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [includeArchived]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">
            Studio · Custom Bidding
          </h1>
          <p className="mt-1 text-sm text-ink-400">
            Genera script DV360 muovendo i tre slider Performance · Quality ·
            Reach. Ogni script viene simulato su 5k impression sintetiche
            prima di essere caricato.
          </p>
        </div>
        <Link
          href="/studio/new"
          className="rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700"
        >
          Crea nuovo script
        </Link>
      </header>

      <div className="mb-4 flex items-center gap-3 text-xs text-ink-400">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          Mostra solo archiviati
        </label>
      </div>

      {loading && <p className="text-sm text-ink-400">Carico…</p>}
      {error && <p className="text-sm text-rose-400">{error}</p>}

      {!loading && !error && scripts.length === 0 && (
        <div className="rounded-lg border border-dashed border-ink-800 p-8 text-center text-sm text-ink-400">
          Nessuno script ancora. Premi <strong>Crea nuovo script</strong> per
          iniziare.
        </div>
      )}

      {!loading && !error && scripts.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-ink-800">
          <table className="w-full text-sm">
            <thead className="bg-ink-800 text-xs uppercase text-ink-400">
              <tr>
                <th className="px-4 py-2 text-left">Nome</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-left">Pesi</th>
                <th className="px-4 py-2 text-left">SHA</th>
                <th className="px-4 py-2 text-left">Size</th>
                <th className="px-4 py-2 text-left">Creato</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {scripts.map((s) => (
                <tr
                  key={s.id}
                  className="hover:bg-ink-800/50"
                >
                  <td className="px-4 py-2">
                    <Link
                      href={`/studio/scripts/${s.id}`}
                      className="text-accent-400 hover:underline"
                    >
                      {s.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-200">
                    P{s.weights.performance} · Q{s.weights.quality} · R
                    {s.weights.reach}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-400">
                    {s.scriptSha256.slice(0, 12)}
                  </td>
                  <td className="px-4 py-2 text-ink-200">
                    {Math.round(s.sizeBytes / 10) / 100} KB
                  </td>
                  <td className="px-4 py-2 text-ink-400">
                    {new Date(s.createdAt).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
