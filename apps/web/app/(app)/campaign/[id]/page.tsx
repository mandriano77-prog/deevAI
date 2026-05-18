/**
 * Campaign-level drill-down — middle layer of the hierarchy.
 *
 * Shows aggregated KPIs for one Order/Campaign, plus the list of its
 * Line Items. Decisions are surfaced as a CTA — they still live at LI level.
 */
import Link from "next/link";
import { notFound } from "next/navigation";

import { CpvTrendChart } from "@/components/cpv-trend-chart";
import { KpiGrid } from "@/components/kpi-grid";
import { ScopeTrail } from "@/components/scope-trail";
import { Topbar } from "@/components/topbar";
import {
  getCampaignById,
  mockBrand,
  mockCampaignTrend,
  mockDecisions,
} from "@/lib/mock-data";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function CampaignPage({ params }: PageProps) {
  const { id } = await params;
  const campaign = getCampaignById(id);
  if (!campaign) return notFound();

  const pendingInCampaign = mockDecisions.filter(
    (d) =>
      d.status === "proposed" &&
      campaign.lineItems.some((li) => li.id === d.lineItemId),
  ).length;

  return (
    <>
      <Topbar
        title={campaign.name}
        subtitle={`Campagna · ${campaign.lineItems.length} line item · pacing ${Math.round(
          campaign.pacingPct * 100,
        )}%`}
      />

      <main className="space-y-8 p-8">
        <ScopeTrail
          brand={{ id: mockBrand.id, name: mockBrand.name }}
          campaign={{ id: campaign.id, name: campaign.name }}
        />

        <section>
          <h2 className="mb-3 text-xs uppercase tracking-wider text-ink-400">
            Performance settimana · {campaign.weekLabel}
          </h2>
          <KpiGrid
            kpi={campaign.kpi}
            delta={campaign.delta}
            budgetTotal={campaign.budgetTotal}
          />
        </section>

        <section className="rounded-lg border border-ink-800 bg-ink-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium text-ink-50">
              CPV — ultime 8 settimane
            </h2>
            <span className="text-xs text-ink-400">
              target {campaign.kpi.cpvTarget.toFixed(2)} €
            </span>
          </div>
          <CpvTrendChart points={mockCampaignTrend} target={campaign.kpi.cpvTarget} />
        </section>

        <section>
          <h2 className="mb-3 text-xs uppercase tracking-wider text-ink-400">
            Line item della campagna
          </h2>
          <div className="overflow-hidden rounded-lg border border-ink-800">
            <table className="w-full text-sm">
              <thead className="bg-ink-800 text-xs uppercase tracking-wider text-ink-400">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Nome</th>
                  <th className="px-4 py-2 text-right font-medium">CPV</th>
                  <th className="px-4 py-2 text-right font-medium">Visite</th>
                  <th className="px-4 py-2 text-right font-medium">Spend</th>
                  <th className="px-4 py-2 text-right font-medium">Max bid</th>
                  <th className="px-4 py-2 text-right font-medium">Pacing</th>
                  <th className="px-4 py-2 text-right font-medium">Modalità</th>
                  <th className="px-4 py-2 text-right font-medium">Decisioni</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {campaign.lineItems.map((li) => (
                  <tr key={li.id} className="bg-ink-900 hover:bg-ink-800/50">
                    <td className="px-4 py-3">
                      <Link
                        href={`/line-item/${li.id}`}
                        className="font-medium text-accent-400 hover:text-accent-300"
                      >
                        {li.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-ink-100">
                      {li.kpi.cpv.toFixed(2)} €
                    </td>
                    <td className="px-4 py-3 text-right text-ink-200">
                      {li.kpi.visits.toLocaleString("it-IT")}
                    </td>
                    <td className="px-4 py-3 text-right text-ink-200">
                      {li.kpi.spend.toLocaleString("it-IT", { maximumFractionDigits: 0 })} €
                    </td>
                    <td className="px-4 py-3 text-right text-ink-300">
                      {li.maxBid.toFixed(2)} €
                    </td>
                    <td className="px-4 py-3 text-right text-ink-300">
                      {Math.round(li.pacingPct * 100)}%
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-ink-400">
                      {li.mode === "observation_only" && "Osservazione"}
                      {li.mode === "approval_required" && "Approvazione"}
                      {li.mode === "auto_apply" && "Auto-apply"}
                    </td>
                    <td className="px-4 py-3 text-right text-ink-200">
                      {li.decisionsPending > 0 ? (
                        <span className="rounded-full bg-accent-900/40 px-2 py-0.5 text-xs text-accent-400">
                          {li.decisionsPending}
                        </span>
                      ) : (
                        <span className="text-ink-500">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {pendingInCampaign > 0 ? (
          <section className="rounded-lg border border-accent-700 bg-accent-900/30 p-4 text-sm text-ink-200">
            {pendingInCampaign} decisioni in attesa sui line item di questa
            campagna.{" "}
            <Link
              href="/decisions"
              className="ml-2 font-medium text-accent-400 hover:text-accent-300"
            >
              Rivedile →
            </Link>
          </section>
        ) : null}
      </main>
    </>
  );
}
