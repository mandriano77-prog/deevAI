"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  studio,
  type ScriptRead,
  type SimulationReport,
} from "@/lib/api";

/**
 * 3-slider wizard for generating a Custom Bidding script.
 *
 * UX rules
 * --------
 * - The three sliders Performance / Quality / Reach are kept consistent
 *   by an auto-redistribute helper: when the user moves one, the *other
 *   two* shrink proportionally so the sum stays at 100.
 * - The preview (sha256 + size) is fetched live with an 800 ms debounce
 *   *only* once a name has been entered and the weights sum to 100 —
 *   we never spam the API while the user is dragging.
 * - "Simula" runs ``POST /v1/studio/scripts/{id}/simulate`` and renders
 *   the score distribution + top winners/losers in cards.
 * - "Salva e chiudi" redirects to the detail page; the script is
 *   already persisted by the preview step, so this is just navigation.
 */
export function StudioNewClient() {
  const router = useRouter();

  // Form state
  const [name, setName] = useState("");
  const [weights, setWeights] = useState({
    performance: 50,
    quality: 30,
    reach: 20,
  });

  // Live preview state
  const [preview, setPreview] = useState<ScriptRead | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Simulation state
  const [simulation, setSimulation] = useState<SimulationReport | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);

  // Names live in their own counter so we can rename the preview row
  // server-side on the fly. Two strategies:
  //   (a) generate one row, then rename via PATCH — but we explicitly
  //       don't expose PATCH (the script_source is server-owned).
  //   (b) create a *new* row every time the name changes, using a
  //       monotonic suffix when needed to dodge the unique constraint.
  //
  // We pick (b) — wasted draft rows are cheap (a few KB each) and the
  // alternative would require a PATCH that opens an attack surface
  // (someone could submit hand-crafted DSL).
  const previewSuffix = useRef(0);

  const sum = weights.performance + weights.quality + weights.reach;
  const validForPreview = name.trim().length > 0 && sum === 100;

  // ─────────────────────────── slider helpers
  // Auto-redistribute on slider change: take the delta from the moved
  // slider, distribute the negative delta across the other two pro-rata.

  const setWeight = (key: keyof typeof weights, raw: number) => {
    const next = Math.max(0, Math.min(100, Math.round(raw)));
    setWeights((cur) => {
      const others = (["performance", "quality", "reach"] as const).filter(
        (k) => k !== key,
      );
      const otherSum = others.reduce((acc, k) => acc + cur[k], 0);
      const targetOtherSum = 100 - next;

      if (otherSum === 0) {
        // Edge case: the other two were both zero — split the
        // remainder evenly so the sum stays at 100.
        const half = Math.floor(targetOtherSum / 2);
        return {
          ...cur,
          [key]: next,
          [others[0]]: half,
          [others[1]]: targetOtherSum - half,
        } as typeof cur;
      }

      // Scale the other two proportionally to their current weights.
      const scale = targetOtherSum / otherSum;
      const a = Math.round(cur[others[0]] * scale);
      const b = targetOtherSum - a; // close the rounding gap
      return {
        ...cur,
        [key]: next,
        [others[0]]: a,
        [others[1]]: b,
      } as typeof cur;
    });
  };

  // ─────────────────────────── debounced live preview

  useEffect(() => {
    if (!validForPreview) {
      setPreview(null);
      setSimulation(null);
      return;
    }

    const handle = window.setTimeout(async () => {
      setPreviewing(true);
      setPreviewError(null);
      setSimulation(null);
      try {
        // We pick a unique-ish name to dodge the (tenant_id, name)
        // unique constraint when the user is iterating quickly.
        previewSuffix.current += 1;
        const previewName = `${name.trim()} (draft #${previewSuffix.current})`;
        const created = await studio.createScript({
          name: previewName,
          weights,
        });
        setPreview(created);
      } catch (e) {
        const msg =
          e instanceof ApiError ? `Errore API (${e.status})` : "Errore di rete";
        setPreviewError(msg);
        setPreview(null);
      } finally {
        setPreviewing(false);
      }
    }, 800);
    return () => window.clearTimeout(handle);
    // We intentionally don't depend on previewSuffix; it's a ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, weights.performance, weights.quality, weights.reach]);

  // ─────────────────────────── actions

  const onSimulate = useCallback(async () => {
    if (!preview) return;
    setSimulating(true);
    setSimulationError(null);
    try {
      const report = await studio.simulateScript(preview.id, {});
      setSimulation(report);
    } catch (e) {
      const msg =
        e instanceof ApiError ? `Errore API (${e.status})` : "Errore di rete";
      setSimulationError(msg);
    } finally {
      setSimulating(false);
    }
  }, [preview]);

  const onSaveAndClose = useCallback(() => {
    if (!preview) return;
    router.push(`/studio/scripts/${preview.id}`);
  }, [preview, router]);

  // ─────────────────────────── render

  return (
    <div className="p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-ink-50">
          Nuovo script Custom Bidding
        </h1>
        <p className="mt-1 text-sm text-ink-400">
          Imposta i tre obiettivi, vedi l&apos;anteprima dello script generato e
          simula la distribuzione di score su 5k impression sintetiche.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* Left — form */}
        <div>
          <label className="mb-4 block">
            <span className="mb-1 block text-xs uppercase tracking-wide text-ink-400">
              Nome script
            </span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Es. Promo Estate IT"
              className="w-full rounded-md border border-ink-800 bg-ink-900 px-3 py-2 text-sm text-ink-50 outline-none focus:border-accent-600"
            />
          </label>

          <SliderRow
            label="Performance"
            description="Premia impression che convertono."
            value={weights.performance}
            onChange={(v) => setWeight("performance", v)}
          />
          <SliderRow
            label="Quality"
            description="Premia viewability, completion-rate, time-on-screen."
            value={weights.quality}
            onChange={(v) => setWeight("quality", v)}
          />
          <SliderRow
            label="Reach"
            description="Premia copertura su nuove utenze e device."
            value={weights.reach}
            onChange={(v) => setWeight("reach", v)}
          />

          <div className="mt-3 text-xs text-ink-400">
            Somma:{" "}
            <span
              className={
                sum === 100 ? "text-accent-400" : "text-rose-400"
              }
            >
              {sum} / 100
            </span>
          </div>

          {/* Actions */}
          <div className="mt-6 flex gap-3">
            <button
              onClick={onSimulate}
              disabled={!preview || simulating}
              className="rounded-md bg-ink-800 px-4 py-2 text-sm text-ink-50 hover:bg-ink-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {simulating ? "Simulo…" : "Simula"}
            </button>
            <button
              onClick={onSaveAndClose}
              disabled={!preview}
              className="rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Salva e chiudi
            </button>
          </div>
        </div>

        {/* Right — preview + simulation */}
        <div className="space-y-6">
          {/* Preview card */}
          <div className="rounded-lg border border-ink-800 bg-ink-900 p-4">
            <h2 className="mb-2 text-sm font-semibold text-ink-50">
              Anteprima script
            </h2>
            {!validForPreview && (
              <p className="text-xs text-ink-400">
                Inserisci un nome e imposta i pesi (somma = 100) per vedere
                l&apos;anteprima.
              </p>
            )}
            {previewing && (
              <p className="text-xs text-ink-400">Genero anteprima…</p>
            )}
            {previewError && (
              <p className="text-xs text-rose-400">{previewError}</p>
            )}
            {preview && !previewing && !previewError && (
              <dl className="space-y-1 text-xs text-ink-200">
                <div className="flex justify-between">
                  <dt className="text-ink-400">sha256</dt>
                  <dd className="font-mono">{preview.scriptSha256.slice(0, 24)}…</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">size</dt>
                  <dd>{preview.sizeBytes} bytes</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-400">status</dt>
                  <dd>{preview.status}</dd>
                </div>
              </dl>
            )}
          </div>

          {/* Simulation card */}
          <div className="rounded-lg border border-ink-800 bg-ink-900 p-4">
            <h2 className="mb-2 text-sm font-semibold text-ink-50">
              Simulazione
            </h2>
            {!simulation && !simulating && !simulationError && (
              <p className="text-xs text-ink-400">
                Clicca <strong>Simula</strong> per vedere la distribuzione su
                5k impression sintetiche.
              </p>
            )}
            {simulating && (
              <p className="text-xs text-ink-400">Eseguo simulazione…</p>
            )}
            {simulationError && (
              <p className="text-xs text-rose-400">{simulationError}</p>
            )}
            {simulation && <SimulationCard report={simulation} />}
          </div>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────── presentational

function SliderRow({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-4">
      <div className="mb-1 flex items-baseline justify-between">
        <div>
          <span className="text-sm font-medium text-ink-50">{label}</span>
          <span className="ml-2 text-xs text-ink-400">{description}</span>
        </div>
        <span className="font-mono text-sm text-ink-50">{value}</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-accent-600"
      />
    </div>
  );
}

export function SimulationCard({ report }: { report: SimulationReport }) {
  const dist = report.distribution;
  return (
    <div className="space-y-4 text-xs text-ink-200">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Scored" value={report.nScored.toLocaleString()} />
        <Stat label="Excluded" value={report.nExcluded.toLocaleString()} />
        <Stat
          label="% > 500"
          value={`${report.pctAbove500.toFixed(1)}%`}
        />
      </div>

      <div>
        <div className="mb-1 text-ink-400">Percentili score</div>
        <div className="grid grid-cols-6 gap-2 font-mono">
          <Pctile label="p10" v={dist.p10} />
          <Pctile label="p25" v={dist.p25} />
          <Pctile label="p50" v={dist.p50} />
          <Pctile label="p75" v={dist.p75} />
          <Pctile label="p90" v={dist.p90} />
          <Pctile label="p99" v={dist.p99} />
        </div>
        <div className="mt-2 text-ink-400">
          μ = {dist.mean.toFixed(1)} · σ = {dist.stddev.toFixed(1)}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <WinnersList title="Top winners" rows={report.topWinners} />
        <WinnersList title="Top losers" rows={report.topLosers} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-ink-800 px-3 py-2">
      <div className="text-ink-400">{label}</div>
      <div className="text-base text-ink-50">{value}</div>
    </div>
  );
}

function Pctile({ label, v }: { label: string; v: number }) {
  return (
    <div className="rounded-md bg-ink-800 px-2 py-1 text-center">
      <div className="text-ink-400">{label}</div>
      <div className="text-ink-50">{v.toFixed(0)}</div>
    </div>
  );
}

function WinnersList({
  title,
  rows,
}: {
  title: string;
  rows: { impressionId: string; score: number; usedSignals: string[] }[];
}) {
  return (
    <div>
      <div className="mb-1 text-ink-400">{title}</div>
      {rows.length === 0 ? (
        <div className="text-ink-400">—</div>
      ) : (
        <ul className="space-y-1">
          {rows.map((r) => (
            <li
              key={r.impressionId}
              className="flex items-center justify-between gap-2 rounded bg-ink-800 px-2 py-1"
            >
              <span className="truncate font-mono text-[10px] text-ink-200">
                {r.impressionId}
              </span>
              <span className="font-mono text-ink-50">{r.score.toFixed(0)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
