"use client";

import { useCallback, useEffect, useState } from "react";

import { Topbar } from "@/components/topbar";
import {
  ApiError,
  runs,
  settingsApi,
  type RunRead,
  type SettingRead,
  type SettingUpdate,
} from "@/lib/api";
import { actionsApi, type ActionRead } from "@/lib/api/actions";
import {
  optimizationApi,
  type HardConstraintRead,
  type OptimizationStrategyRead,
} from "@/lib/api/optimization";

import { ActionCatalog } from "./_components/ActionCatalog";
import { ActionFunnelBuilder } from "./_components/ActionFunnelBuilder";
import { AgentBehavior } from "./_components/AgentBehavior";
import { HardConstraintsList } from "./_components/HardConstraintsList";
import { OptimizationStrategy } from "./_components/OptimizationStrategy";
import { ModeAndDigest } from "./_components/ModeAndDigest";
import { SafetyFilters } from "./_components/SafetyFilters";
import { StatusHeader } from "./_components/StatusHeader";

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingRead | null>(null);
  const [actions, setActions] = useState<ActionRead[]>([]);
  const [funnel, setFunnel] = useState<ActionRead[]>([]);
  const [strategy, setStrategy] = useState<OptimizationStrategyRead | null>(null);
  const [constraints, setConstraints] = useState<HardConstraintRead[]>([]);
  const [lastRun, setLastRun] = useState<RunRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, act, fn, runList] = await Promise.all([
        settingsApi.get(),
        actionsApi.list(),
        actionsApi.funnel().catch(() => [] as ActionRead[]),
        runs.list({ limit: 1 }),
      ]);
      setSettings(s);
      setActions(act);
      setFunnel(fn);
      setLastRun(runList[0] ?? null);

      try {
        const st = await optimizationApi.getDefault();
        setStrategy(st);
        const cons = await optimizationApi.listConstraints(st.id);
        setConstraints(cons);
      } catch {
        setStrategy(null);
        setConstraints([]);
      }
    } catch (e) {
      setError(
        e instanceof ApiError
          ? "Impossibile caricare le impostazioni"
          : "Errore di connessione",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function patchSettings(partial: SettingUpdate) {
    if (!settings) return;
    const prev = settings;
    setSettings({ ...settings, ...partial });
    setSaving(true);
    setError(null);
    try {
      const updated = await settingsApi.update(partial);
      setSettings(updated);
      showToast("Impostazioni salvate");
    } catch {
      setSettings(prev);
      setError("Salvataggio non riuscito");
    } finally {
      setSaving(false);
    }
  }

  async function upsertStrategy(body: {
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
  }) {
    const prev = strategy;
    const optimistic: OptimizationStrategyRead = {
      id: strategy?.id ?? "pending",
      tenant_id: strategy?.tenant_id ?? "",
      line_item_id: strategy?.line_item_id ?? null,
      status: "active",
      secondary_metric: strategy?.secondary_metric ?? null,
      secondary_target: strategy?.secondary_target ?? null,
      secondary_weight: strategy?.secondary_weight ?? null,
      tertiary_metric: strategy?.tertiary_metric ?? null,
      tertiary_target: strategy?.tertiary_target ?? null,
      tertiary_weight: strategy?.tertiary_weight ?? null,
      primary_action_id: strategy?.primary_action_id ?? null,
      ...body,
    };
    setStrategy(optimistic);
    setSaving(true);
    setError(null);
    try {
      const st = await optimizationApi.upsertDefault(body);
      setStrategy(st);
      const cons = await optimizationApi.listConstraints(st.id);
      setConstraints(cons);
      showToast("Strategia salvata");
    } catch {
      setStrategy(prev);
      setError("Salvataggio strategia non riuscito");
    } finally {
      setSaving(false);
    }
  }

  async function createConstraint(body: {
    metric: string;
    operator: string;
    value: number;
    violation_policy: string;
  }) {
    if (!strategy) return;
    const prev = constraints;
    setConstraints([
      ...constraints,
      {
        id: `temp-${Date.now()}`,
        tenant_id: strategy.tenant_id,
        optimization_strategy_id: strategy.id,
        status: "active",
        ...body,
      },
    ]);
    setError(null);
    try {
      await optimizationApi.createConstraint(strategy.id, body);
      setConstraints(await optimizationApi.listConstraints(strategy.id));
      showToast("Constraint aggiunto");
    } catch {
      setConstraints(prev);
      setError("Constraint non salvato");
    }
  }

  async function removeConstraint(id: string) {
    const prev = constraints;
    setConstraints(constraints.filter((c) => c.id !== id));
    setError(null);
    try {
      await optimizationApi.deleteConstraint(id);
      if (strategy) {
        setConstraints(await optimizationApi.listConstraints(strategy.id));
      }
      showToast("Constraint rimosso");
    } catch {
      setConstraints(prev);
      setError("Rimozione non riuscita");
    }
  }

  async function reorderFunnel(ids: string[]) {
    const prev = funnel;
    setFunnel(
      ids
        .map((id) => actions.find((a) => a.id === id))
        .filter((a): a is ActionRead => Boolean(a)),
    );
    setError(null);
    try {
      const next = await actionsApi.setFunnel(ids);
      setFunnel(next);
      showToast("Funnel aggiornato");
    } catch {
      setFunnel(prev);
      setError("Funnel non salvato");
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Topbar
        title="Settings"
        subtitle="Action, strategia multi-obiettivo e parametri agente"
      />
      {settings ? (
        <StatusHeader
          settings={settings}
          constraints={constraints}
          lastRun={lastRun}
        />
      ) : null}

      <main className="space-y-10 p-8" id="main-content">
        {loading ? <p className="text-sm text-ink-400">Caricamento…</p> : null}
        {error ? (
          <div
            role="alert"
            className="rounded-md border border-red-900/50 bg-red-900/20 px-4 py-3 text-sm text-red-200"
          >
            {error}
          </div>
        ) : null}
        {toast ? (
          <div
            role="status"
            className="rounded-md border border-amber-800/50 bg-amber-900/20 px-4 py-3 text-sm text-amber-200"
          >
            {toast}
          </div>
        ) : null}

        {!loading && settings ? (
          <>
            <ActionCatalog
              actions={actions}
              onCreate={async (data) => {
                await actionsApi.create(data);
                await load();
                showToast("Action creata");
              }}
              onUpdate={async (id, data) => {
                const prev = actions;
                setActions(
                  actions.map((a) => (a.id === id ? { ...a, ...data } : a)),
                );
                try {
                  await actionsApi.update(id, data);
                  showToast("Action aggiornata");
                } catch {
                  setActions(prev);
                  setError("Aggiornamento action non riuscito");
                }
              }}
              onArchive={async (id) => {
                const prev = actions;
                setActions(actions.filter((a) => a.id !== id));
                try {
                  await actionsApi.remove(id);
                  showToast("Action archiviata");
                } catch {
                  setActions(prev);
                  setError("Archiviazione non riuscita");
                }
              }}
            />

            <ActionFunnelBuilder funnel={funnel} onReorder={reorderFunnel} />

            <OptimizationStrategy
              strategy={strategy}
              saving={saving}
              onUpsert={upsertStrategy}
            />

            <HardConstraintsList
              strategyId={strategy?.id ?? null}
              constraints={constraints}
              onCreate={createConstraint}
              onDelete={removeConstraint}
            />

            <AgentBehavior data={settings} saving={saving} onPatch={patchSettings} />
            <SafetyFilters data={settings} saving={saving} onPatch={patchSettings} />
            <ModeAndDigest data={settings} saving={saving} onPatch={patchSettings} />
          </>
        ) : null}
      </main>
    </div>
  );
}
