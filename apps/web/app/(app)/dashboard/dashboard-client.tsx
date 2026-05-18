"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CpvTrendChart } from "@/components/cpv-trend-chart";
import { KpiGrid } from "@/components/kpi-grid";
import { LineItemSetup } from "@/components/line-item-setup";
import { Topbar } from "@/components/topbar";
import {
  ApiError,
  integrations,
  lineItems,
  runs,
  tenants,
  type IntegrationRead,
  type LineItemRead,
  type RunRead,
  type TenantRead,
} from "@/lib/api";
import { runToKpi, runToTrend } from "@/lib/map-api";

export function DashboardClient() {
  const [tenant, setTenant] = useState<TenantRead | null>(null);
  const [integrationList, setIntegrationList] = useState<IntegrationRead[]>([]);
  const [items, setItems] = useState<LineItemRead[]>([]);
  const [latestRun, setLatestRun] = useState<RunRead | null>(null);
  const [pendingDecisions, setPendingDecisions] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [me, ints, lis, runList] = await Promise.all([
        tenants.me(),
        integrations.list(),
        lineItems.list(),
        runs.list({ limit: 1 }),
      ]);
      setTenant(me);
      setIntegrationList(ints);
      setItems(lis);
      const run = runList[0] ?? null;
      setLatestRun(run);

      if (run) {
        const decisions = await runs.decisions(run.id);
        setPendingDecisions(
          decisions.filter((d) => d.status === "proposed").length,
        );
      } else {
        setPendingDecisions(0);
      }
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? `Errore API (${e.status})`
          : "Impossibile caricare la dashboard";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const brandName = tenant?.name ?? "Workspace";
  const weekLabel = latestRun?.week_label ?? "—";
  const kpi = runToKpi(latestRun);
  const trend = runToTrend(latestRun);
  const connectedIntegrations = integrationList.filter(
    (i) => i.status === "connected",
  ).length;

  const showEmptyRun =
    !loading && !error && items.length > 0 && !latestRun;
  const showNoLineItems = !loading && !error && items.length === 0;

  return (
    <>
      <Topbar
        title={brandName}
        subtitle={`Vista brand · ${connectedIntegrations} integrazioni · settimana ${weekLabel}`}
        lineItems={items}
        onRunComplete={load}
      />

      <main className="space-y-8 p-8">
        {loading ? (
          <p className="text-sm text-ink-400">Caricamento…</p>
        ) : null}

        {error ? (
          <div className="rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        {showNoLineItems ? (
          <section className="rounded-lg border border-ink-800 bg-ink-900 p-8 text-center">
            <h2 className="text-lg font-medium text-ink-50">
              Registra il primo line item
            </h2>
            <p className="mt-2 text-sm text-ink-400">
              Inserisci gli ID dalla console DSP (advertiser, line item, ad group).
            </p>
            <LineItemSetup
              integrations={integrationList}
              onCreated={() => void load()}
            />
            <Link
              href="/onboarding"
              className="mt-6 inline-block text-sm text-accent-400 hover:text-accent-300"
            >
              Oppure collega la DSP →
            </Link>
          </section>
        ) : null}

        {showEmptyRun ? (
          <section className="rounded-lg border border-dashed border-ink-700 bg-ink-900/50 p-8 text-center">
            <h2 className="text-lg font-medium text-ink-50">
              Avvia il primo run
            </h2>
            <p className="mt-2 text-sm text-ink-400">
              Hai {items.length} line item pronti. Usa &quot;Avvia nuovo run&quot; in
              alto a destra per generare decisioni e digest.
            </p>
          </section>
        ) : null}

        {!showNoLineItems && !error ? (
          <>
            <section>
              <h2 className="mb-3 text-xs uppercase tracking-wider text-ink-400">
                Performance settimana
              </h2>
              {latestRun ? (
                <KpiGrid kpi={kpi} />
              ) : (
                <p className="text-sm text-ink-400">
                  KPI disponibili dopo il primo run.
                </p>
              )}
            </section>

            <section className="grid grid-cols-1 gap-3 lg:grid-cols-[1.4fr_1fr]">
              <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-sm font-medium text-ink-50">
                    CPV — ultime settimane
                  </h2>
                  <span className="text-xs text-ink-400">
                    target {kpi.cpvTarget.toFixed(2)} €
                  </span>
                </div>
                {trend.length > 0 ? (
                  <CpvTrendChart points={trend} target={kpi.cpvTarget} />
                ) : (
                  <p className="text-sm text-ink-400">
                    Trend disponibile dopo il primo run.
                  </p>
                )}
              </div>

              <div className="rounded-lg border border-ink-800 bg-ink-900 p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-medium text-ink-50">
                    Riepilogo del lunedì
                  </h2>
                  <span className="text-xs text-ink-400">{weekLabel}</span>
                </div>
                {latestRun?.digest_text ? (
                  <div className="space-y-3 text-sm leading-relaxed text-ink-200">
                    {latestRun.digest_text.split("\n\n").map((paragraph, i) => (
                      <p key={i}>{paragraph}</p>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-ink-400">
                    Il digest compare dopo il primo run.
                  </p>
                )}
              </div>
            </section>

            <section>
              <h2 className="mb-3 text-xs uppercase tracking-wider text-ink-400">
                Line item attivi
              </h2>
              <div className="overflow-hidden rounded-lg border border-ink-800">
                <table className="w-full text-sm">
                  <thead className="bg-ink-800 text-xs uppercase tracking-wider text-ink-400">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Nome</th>
                      <th className="px-4 py-2 text-right font-medium">
                        Target CPV
                      </th>
                      <th className="px-4 py-2 text-right font-medium">Modalità</th>
                      <th className="px-4 py-2 text-right font-medium">Stato</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-800">
                    {items.map((li) => (
                      <tr
                        key={li.id}
                        className="bg-ink-900 hover:bg-ink-800/50"
                      >
                        <td className="px-4 py-3">
                          <Link
                            href={`/line-item/${li.id}`}
                            className="font-medium text-accent-400 hover:text-accent-300"
                          >
                            {li.name}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-ink-100">
                          {li.cpv_target.toFixed(2)} €
                        </td>
                        <td className="px-4 py-3 text-right text-ink-300">
                          {li.mode.replace(/_/g, " ")}
                        </td>
                        <td className="px-4 py-3 text-right text-ink-300">
                          {li.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {pendingDecisions > 0 ? (
              <section className="rounded-lg border border-accent-700 bg-accent-900/30 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-ink-50">
                      {pendingDecisions} decisioni in attesa di approvazione
                    </h3>
                    <p className="mt-1 text-xs text-ink-300">
                      Rivedi e approva dal feed decisioni.
                    </p>
                  </div>
                  <Link
                    href="/decisions"
                    className="rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-ink-50 hover:bg-accent-700"
                  >
                    Rivedi e approva →
                  </Link>
                </div>
              </section>
            ) : null}
          </>
        ) : null}
      </main>
    </>
  );
}
