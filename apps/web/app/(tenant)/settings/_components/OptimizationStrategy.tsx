"use client";

import { useState } from "react";

import type { OptimizationStrategyRead } from "@/lib/api/optimization";
import { microcopy, sectionCls, selectCls, SettingRow } from "./shared";

interface UpsertBody {
  mode: string;
  primary_metric: string;
  primary_target: number;
  primary_weight: number;
  secondary_metric?: string | null;
  secondary_target?: number | null;
  secondary_weight?: number | null;
  tertiary_metric?: string | null;
  tertiary_target?: number | null;
  tertiary_weight?: number | null;
  tolerance_band: number;
}

interface Props {
  strategy: OptimizationStrategyRead | null;
  saving: boolean;
  onUpsert: (body: UpsertBody) => Promise<void>;
}

const METRICS = ["cpv", "cpc", "cpcv", "cpm", "cpa", "roas"] as const;

export function OptimizationStrategy({ strategy, saving, onUpsert }: Props) {
  const [mode, setMode] = useState(strategy?.mode ?? "single");
  const [primaryMetric, setPrimaryMetric] = useState(strategy?.primary_metric ?? "cpv");
  const [primaryTarget, setPrimaryTarget] = useState(strategy?.primary_target ?? 0.5);
  const [primaryWeight, setPrimaryWeight] = useState(strategy?.primary_weight ?? 100);
  const [secondaryMetric, setSecondaryMetric] = useState(strategy?.secondary_metric ?? "cpc");
  const [secondaryTarget, setSecondaryTarget] = useState(strategy?.secondary_target ?? 0.1);
  const [secondaryWeight, setSecondaryWeight] = useState(strategy?.secondary_weight ?? 30);
  const [tertiaryMetric, setTertiaryMetric] = useState(strategy?.tertiary_metric ?? "cpm");
  const [tertiaryTarget, setTertiaryTarget] = useState(strategy?.tertiary_target ?? 5.0);
  const [tertiaryWeight, setTertiaryWeight] = useState(strategy?.tertiary_weight ?? 10);
  const band = strategy?.tolerance_band ?? 0.2;

  function rebalanceBlended3(primary: number, secondary: number) {
    const p = Math.min(100, Math.max(0, primary));
    const s = Math.min(100 - p, Math.max(0, secondary));
    setPrimaryWeight(p);
    setSecondaryWeight(s);
    setTertiaryWeight(100 - p - s);
  }

  function buildBody(): UpsertBody {
    const body: UpsertBody = {
      mode,
      primary_metric: primaryMetric,
      primary_target: primaryTarget,
      primary_weight: mode === "single" ? 100 : primaryWeight,
      tolerance_band: band,
    };
    if (mode === "blended_2" || mode === "blended_3") {
      body.secondary_metric = secondaryMetric;
      body.secondary_target = secondaryTarget;
      body.secondary_weight = secondaryWeight;
    }
    if (mode === "blended_3") {
      body.tertiary_metric = tertiaryMetric;
      body.tertiary_target = tertiaryTarget;
      body.tertiary_weight = tertiaryWeight;
    }
    return body;
  }

  return (
    <section aria-labelledby="strategy-heading">
      <h2 id="strategy-heading" className="mb-2 text-sm font-medium text-ink-50">
        Strategia di ottimizzazione (metric-agnostic)
      </h2>
      <div className={sectionCls}>
        <SettingRow label="Modalità" hint="single o blended fino a 3 KPI">
          <select
            className={selectCls}
            disabled={saving}
            value={mode}
            aria-label="Modalità strategia"
            onChange={(e) => {
              setMode(e.target.value);
              void onUpsert({ ...buildBody(), mode: e.target.value });
            }}
          >
            <option value="single">Singola metrica</option>
            <option value="blended_2">Blended 2 KPI</option>
            <option value="blended_3">Blended 3 KPI</option>
          </select>
        </SettingRow>
        <SettingRow label="Metrica primaria">
          <select
            className={selectCls}
            value={primaryMetric}
            disabled={saving}
            aria-label="Metrica primaria"
            onChange={(e) => {
              setPrimaryMetric(e.target.value);
              void onUpsert({ ...buildBody(), primary_metric: e.target.value });
            }}
          >
            {METRICS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Target primario">
          <input
            type="number"
            step="0.01"
            className={selectCls}
            disabled={saving}
            value={primaryTarget}
            aria-label="Target primario"
            onChange={(e) => setPrimaryTarget(Number(e.target.value))}
            onBlur={() => void onUpsert(buildBody())}
          />
        </SettingRow>
        {mode !== "single" ? (
          <>
            <SettingRow label="Peso primario %" hint="Somma pesi = 100">
              <input
                type="range"
                min={0}
                max={mode === "blended_3" ? 80 : 100}
                value={primaryWeight}
                disabled={saving}
                aria-label="Peso metrica primaria"
                onChange={(e) => {
                  const w = Number(e.target.value);
                  if (mode === "blended_3") {
                    rebalanceBlended3(w, secondaryWeight);
                  } else {
                    setPrimaryWeight(w);
                    setSecondaryWeight(100 - w);
                  }
                }}
                onMouseUp={() => void onUpsert(buildBody())}
                onTouchEnd={() => void onUpsert(buildBody())}
              />
              <span className="ml-2 text-sm text-ink-300">{primaryWeight}%</span>
            </SettingRow>
            <SettingRow label="Metrica secondaria">
              <select
                className={selectCls}
                value={secondaryMetric}
                disabled={saving}
                aria-label="Metrica secondaria"
                onChange={(e) => {
                  setSecondaryMetric(e.target.value);
                  void onUpsert({ ...buildBody(), secondary_metric: e.target.value });
                }}
              >
                {METRICS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </SettingRow>
            <SettingRow label="Target secondario">
              <input
                type="number"
                step="0.01"
                className={selectCls}
                disabled={saving}
                value={secondaryTarget}
                aria-label="Target secondario"
                onChange={(e) => setSecondaryTarget(Number(e.target.value))}
                onBlur={() => void onUpsert(buildBody())}
              />
            </SettingRow>
            {mode === "blended_2" ? (
              <p className="text-xs text-ink-500">Secondario: {secondaryWeight}%</p>
            ) : null}
            {mode === "blended_3" ? (
              <>
                <SettingRow label="Peso secondario %">
                  <input
                    type="range"
                    min={0}
                    max={100 - primaryWeight}
                    value={secondaryWeight}
                    disabled={saving}
                    aria-label="Peso metrica secondaria"
                    onChange={(e) => rebalanceBlended3(primaryWeight, Number(e.target.value))}
                    onMouseUp={() => void onUpsert(buildBody())}
                    onTouchEnd={() => void onUpsert(buildBody())}
                  />
                  <span className="ml-2 text-sm text-ink-300">{secondaryWeight}%</span>
                </SettingRow>
                <SettingRow label="Metrica terziaria">
                  <select
                    className={selectCls}
                    value={tertiaryMetric}
                    disabled={saving}
                    aria-label="Metrica terziaria"
                    onChange={(e) => {
                      setTertiaryMetric(e.target.value);
                      void onUpsert({ ...buildBody(), tertiary_metric: e.target.value });
                    }}
                  >
                    {METRICS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </SettingRow>
                <SettingRow label="Target terziario">
                  <input
                    type="number"
                    step="0.01"
                    className={selectCls}
                    disabled={saving}
                    value={tertiaryTarget}
                    aria-label="Target terziario"
                    onChange={(e) => setTertiaryTarget(Number(e.target.value))}
                    onBlur={() => void onUpsert(buildBody())}
                  />
                </SettingRow>
                <p className="text-xs text-ink-500">Terziario: {tertiaryWeight}%</p>
              </>
            ) : null}
          </>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-ink-500">{microcopy}</p>
    </section>
  );
}
