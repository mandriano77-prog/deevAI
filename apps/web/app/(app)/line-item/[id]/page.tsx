/**
 * Line Item-level drill-down — the deepest layer.
 *
 * This is where the bidagent operates: every term that the agent
 * modifies (domain, app, device, region, audience, daypart) is shown
 * here as a breakdown. Bid adjustments live at this level in Google DV360.
 *
 * The page renders 5 dimension tables + a 24×7 daypart heatmap +
 * a section listing the decisions proposed for this specific LI.
 */
import Link from "next/link";
import { notFound } from "next/navigation";

import { CpvTrendChart } from "@/components/cpv-trend-chart";
import { DecisionsTable } from "@/components/decisions-table";
import { DaypartHeatmap, DimensionTable } from "@/components/dimension-breakdown";
import { KpiGrid } from "@/components/kpi-grid";
import { ScopeTrail } from "@/components/scope-trail";
import { Topbar } from "@/components/topbar";
import {
  getCampaignById,
  getDecisionsForLineItem,
  getLineItemById,
  mockBrand,
  mockLineItemTrend,
} from "@/lib/mock-data";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function LineItemPage({ params }: PageProps) {
  const { id } = await params;
  const lineItem = getLineItemById(id);
  if (!lineItem) return notFound();
  const campaign = getCampaignById(lineItem.campaignId);
  const decisions = getDecisionsForLineItem(lineItem.id);

  return (
    <>
      <Topbar
        title={lineItem.name}
        subtitle={`Line item · max bid ${lineItem.maxBid.toFixed(2)} € · pacing ${Math.round(
          lineItem.pacingPct * 100,
        )}%`}
      />

      <main className="space-y-8 p-8">
        <ScopeTrail
          brand={{ id: mockBrand.id, name: mockBrand.name }}
          campaign={
            campaign ? { id: campaign.id, name: campaign.name } : undefined
          }
          lineItem={{ name: lineItem.name }}
        />

        <section>
          <h2 className="mb-3 text-xs uppercase tracking-wider text-ink-400">
            Performance settimana · {lineItem.weekLabel}
          </h2>
          <KpiGrid kpi={lineItem.kpi} delta={lineItem.delta} />
        </section>

        <section className="rounded-lg border border-ink-800 bg-ink-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium text-ink-50">
              CPV — ultime 8 settimane
            </h2>
            <span className="text-xs text-ink-400">
              target {lineItem.kpi.cpvTarget.toFixed(2)} €
            </span>
          </div>
          <CpvTrendChart
            points={mockLineItemTrend}
            target={lineItem.kpi.cpvTarget}
          />
        </section>

        {/* Breakdown per dimension — the leverage map */}
        <section className="space-y-3">
          <h2 className="text-xs uppercase tracking-wider text-ink-400">
            Breakdown · dove si può ottimizzare
          </h2>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <DimensionTable
              title="Top domini"
              description="ordinato per CPV"
              rows={[...lineItem.breakdowns.domains].sort((a, b) => b.cpv - a.cpv)}
              cpvTarget={lineItem.kpi.cpvTarget}
            />
            <DimensionTable
              title="Device type"
              rows={lineItem.breakdowns.devices}
              cpvTarget={lineItem.kpi.cpvTarget}
              limit={4}
            />
            <DimensionTable
              title="Regioni"
              description="top per spend"
              rows={lineItem.breakdowns.regions}
              cpvTarget={lineItem.kpi.cpvTarget}
            />
            <DimensionTable
              title="Audiences"
              rows={lineItem.breakdowns.audiences}
              cpvTarget={lineItem.kpi.cpvTarget}
            />
            <DimensionTable
              title="App"
              rows={lineItem.breakdowns.apps}
              cpvTarget={lineItem.kpi.cpvTarget}
            />
            <DaypartHeatmap
              cells={lineItem.breakdowns.dayparts}
              cpvTarget={lineItem.kpi.cpvTarget}
            />
          </div>
        </section>

        {/* Decisions for this Line Item */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs uppercase tracking-wider text-ink-400">
              Decisioni proposte per questo line item
            </h2>
            <Link
              href="/decisions"
              className="text-xs text-accent-400 hover:text-accent-300"
            >
              Vedi tutte le decisioni →
            </Link>
          </div>
          {decisions.length > 0 ? (
            <DecisionsTable rows={decisions} />
          ) : (
            <div className="rounded-lg border border-ink-800 bg-ink-900 p-5 text-sm text-ink-400">
              Nessuna decisione pendente per questa settimana.
            </div>
          )}
        </section>

        {lineItem.mode === "observation_only" ? (
          <div className="rounded-md border border-ink-800 bg-ink-900/50 p-4 text-xs text-ink-400">
            <strong className="font-medium text-ink-200">Observation only.</strong>{" "}
            Per ora le decisioni vengono solo proposte. Dopo il periodo di
            calibrazione il line item passerà a "Richiede approvazione" e le
            modifiche andranno live solo dopo il tuo click.
          </div>
        ) : null}
      </main>
    </>
  );
}
