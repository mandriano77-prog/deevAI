/**
 * Mock data for the dashboard. Replaced by real API calls in Sprint 2.x,
 * keeping the same shape so swapping is cheap.
 *
 * Hierarchy mirrors Google DV360 exactly:
 *   Brand (Advertiser)
 *     └─ Campaign (Order / IO)
 *           └─ LineItem (where bid adjustments live)
 *
 * KPIs are computed for each level. Decisions are always Line Item-scoped
 * because that's where Amazon's bid modifiers live.
 */

// ────────────────────────────────────────────────────────────────
// KPI shapes — Tier 1 (MVP) + Tier 2 (next)
// ────────────────────────────────────────────────────────────────

export interface CoreKpi {
  // Tier 1 — must-have for the bidagent CPV product
  impressions: number;
  clicks: number;
  visits: number;
  spend: number;
  ctr: number; // 0–1
  cpv: number; // currency per visit (Infinity if no visits)
  cpvTarget: number;
  reach: number; // unique users
  viewabilityRate: number; // 0–1
  winRate: number; // 0–1, won bids / attempted bids

  // Tier 2 — next batch, partly populated for richer brands
  conversions?: number;        // post-visit conversions (purchase, lead, ATC)
  roas?: number;               // revenue / spend (if conversions have value)
  frequency?: number;          // avg impressions per unique user
  ntbConversions?: number;     // new-to-brand
}

export interface KpiDelta {
  // Period-over-period deltas, where applicable
  cpvDeltaPct?: number;
  visitsDeltaPct?: number;
  spendDeltaPct?: number;
  reachDeltaPct?: number;
}

// ────────────────────────────────────────────────────────────────
// Hierarchy
// ────────────────────────────────────────────────────────────────

export interface BrandSummary {
  id: string;
  name: string;
  status: "active" | "paused";
  kpi: CoreKpi;
  delta: KpiDelta;
  weekLabel: string;
  campaigns: CampaignSummary[];
  budgetTotal: number;
}

export interface CampaignSummary {
  id: string;
  brandId: string;
  name: string;
  status: "active" | "paused" | "completed";
  kpi: CoreKpi;
  delta: KpiDelta;
  weekLabel: string;
  pacingPct: number;  // 0–1, % of budget consumed
  lineItems: LineItemSummary[];
  budgetTotal: number;
}

export interface LineItemSummary {
  id: string;
  campaignId: string;
  brandId: string;
  name: string;
  status: "active" | "paused";
  mode: "observation_only" | "approval_required" | "auto_apply";
  kpi: CoreKpi;
  delta: KpiDelta;
  weekLabel: string;
  maxBid: number;
  pacingPct: number;
  breakdowns: LineItemBreakdowns;
  decisionsPending: number;
}

export interface LineItemBreakdowns {
  domains: DimensionRow[];      // top by spend
  apps: DimensionRow[];
  devices: DimensionRow[];
  regions: DimensionRow[];
  audiences: DimensionRow[];
  dayparts: DaypartCell[];      // 24×7 grid
}

export interface DimensionRow {
  label: string;
  value: string;
  impressions: number;
  visits: number;
  spend: number;
  cpv: number;
  ctr: number;
  modifier: number;             // current bid modifier 0–N
}

export interface DaypartCell {
  day: number;       // 0=Mon … 6=Sun
  hour: number;      // 0–23
  visits: number;
  spend: number;
  cpv: number;
}

// ────────────────────────────────────────────────────────────────
// Trend (week-over-week)
// ────────────────────────────────────────────────────────────────

export interface TrendPoint {
  weekLabel: string;
  cpv: number;
  visits: number;
  spend: number;
}

// ────────────────────────────────────────────────────────────────
// Decisions
// ────────────────────────────────────────────────────────────────

export type DecisionReason =
  | "anomalous_ctr"
  | "over_target"
  | "under_target"
  | "on_target"
  | "zero_visits"
  | "low_viewability"
  | "insufficient_volume"
  | "exploration_revive";

export interface DecisionRow {
  id: string;
  lineItemId: string;
  module: string;
  key: string;
  value: string;
  label: string;
  previousModifier: number;
  newModifier: number;
  reason: DecisionReason;
  observedCpv: number | null;
  observedVisits: number;
  observedImpressions: number;
  note: string;
  status: "proposed" | "approved" | "rejected" | "applied";
}

// ────────────────────────────────────────────────────────────────
// Mock data instances
// ────────────────────────────────────────────────────────────────

const brandTrend: TrendPoint[] = [
  { weekLabel: "s-7", cpv: 0.85, visits: 2810, spend: 2388.5 },
  { weekLabel: "s-6", cpv: 0.81, visits: 2945, spend: 2385.45 },
  { weekLabel: "s-5", cpv: 0.77, visits: 3110, spend: 2394.7 },
  { weekLabel: "s-4", cpv: 0.74, visits: 3220, spend: 2382.8 },
  { weekLabel: "s-3", cpv: 0.69, visits: 3380, spend: 2332.2 },
  { weekLabel: "s-2", cpv: 0.66, visits: 3470, spend: 2290.2 },
  { weekLabel: "s-1", cpv: 0.63, visits: 3560, spend: 2243.8 },
  { weekLabel: "oggi", cpv: 0.6, visits: 3663, spend: 2197.8 },
];

// Tier 1 + Tier 2 KPIs at Line Item level
const li001Kpi: CoreKpi = {
  impressions: 1_546_000,
  clicks: 9080,
  visits: 3663,
  spend: 2193.63,
  ctr: 0.0059,
  cpv: 0.6,
  cpvTarget: 0.4,
  reach: 412_300,
  viewabilityRate: 0.72,
  winRate: 0.34,
  conversions: 124,
  roas: 2.8,
  frequency: 3.75,
  ntbConversions: 41,
};

const li002Kpi: CoreKpi = {
  impressions: 980_000,
  clicks: 4820,
  visits: 1840,
  spend: 1042.0,
  ctr: 0.0049,
  cpv: 0.57,
  cpvTarget: 0.4,
  reach: 268_400,
  viewabilityRate: 0.69,
  winRate: 0.29,
  conversions: 58,
  roas: 2.4,
  frequency: 3.65,
  ntbConversions: 19,
};

const breakdownsLi001: LineItemBreakdowns = {
  domains: [
    { label: "repubblica.it", value: "repubblica.it", impressions: 92_000, visits: 242, spend: 152, cpv: 0.63, ctr: 0.0064, modifier: 1.0 },
    { label: "corriere.it", value: "corriere.it", impressions: 78_000, visits: 198, spend: 124, cpv: 0.63, ctr: 0.0061, modifier: 1.0 },
    { label: "gazzetta.it", value: "gazzetta.it", impressions: 68_000, visits: 142, spend: 98, cpv: 0.69, ctr: 0.0054, modifier: 1.0 },
    { label: "ilfattoquotidiano.it", value: "ilfattoquotidiano.it", impressions: 54_000, visits: 167, spend: 78, cpv: 0.47, ctr: 0.0058, modifier: 1.0 },
    { label: "ilsole24ore.com", value: "ilsole24ore.com", impressions: 48_000, visits: 128, spend: 72, cpv: 0.56, ctr: 0.0052, modifier: 1.0 },
    { label: "suspicious-clicks.example", value: "suspicious-clicks.example", impressions: 42_000, visits: 12, spend: 28, cpv: 2.33, ctr: 0.061, modifier: 1.0 },
  ],
  apps: [
    { label: "Spotify", value: "com.spotify.spotify", impressions: 64_000, visits: 184, spend: 115, cpv: 0.62, ctr: 0.005, modifier: 1.0 },
    { label: "Twitch", value: "com.twitch.android.app", impressions: 38_000, visits: 26, spend: 85, cpv: 3.27, ctr: 0.0035, modifier: 0.85 },
  ],
  devices: [
    { label: "Mobile", value: "MOBILE", impressions: 520_000, visits: 1061, spend: 625, cpv: 0.59, ctr: 0.006, modifier: 1.15 },
    { label: "Desktop", value: "DESKTOP", impressions: 210_000, visits: 540, spend: 380, cpv: 0.70, ctr: 0.0055, modifier: 1.0 },
    { label: "Connected TV", value: "CTV", impressions: 78_000, visits: 39, spend: 443, cpv: 11.37, ctr: 0.0008, modifier: 1.0 },
    { label: "Tablet", value: "TABLET", impressions: 46_000, visits: 84, spend: 52, cpv: 0.62, ctr: 0.005, modifier: 1.0 },
  ],
  regions: [
    { label: "Lombardia", value: "IT-25", impressions: 170_000, visits: 488, spend: 245, cpv: 0.5, ctr: 0.0064, modifier: 1.0 },
    { label: "Lazio", value: "IT-62", impressions: 105_000, visits: 184, spend: 127, cpv: 0.69, ctr: 0.0055, modifier: 1.0 },
    { label: "Piemonte", value: "IT-21", impressions: 82_000, visits: 172, spend: 99, cpv: 0.58, ctr: 0.0058, modifier: 1.0 },
    { label: "Veneto", value: "IT-34", impressions: 72_000, visits: 165, spend: 84, cpv: 0.51, ctr: 0.0059, modifier: 1.0 },
    { label: "Toscana", value: "IT-52", impressions: 58_000, visits: 134, spend: 71, cpv: 0.53, ctr: 0.0057, modifier: 1.0 },
  ],
  audiences: [
    { label: "In-Market: Smart Home", value: "AUD-IM-CONNESSI", impressions: 110_000, visits: 396, spend: 107, cpv: 0.27, ctr: 0.0075, modifier: 1.0 },
    { label: "Lifestyle: Foodies", value: "AUD-LIFE-FOODIE", impressions: 84_000, visits: 224, spend: 138, cpv: 0.62, ctr: 0.0058, modifier: 1.0 },
    { label: "In-Market: Travel", value: "AUD-IM-TRAVEL", impressions: 62_000, visits: 178, spend: 102, cpv: 0.57, ctr: 0.0056, modifier: 1.0 },
  ],
  // 24×7 grid — populate with patterns: lunch 12-14, prime 18-22 hot, night 0-6 cold
  dayparts: generateDaypartGrid(),
};

function generateDaypartGrid(): DaypartCell[] {
  const cells: DaypartCell[] = [];
  for (let day = 0; day < 7; day++) {
    for (let hour = 0; hour < 24; hour++) {
      let intensity = 0.2;
      if (hour >= 18 && hour <= 22) intensity = 0.95;       // prime evening
      else if (hour >= 12 && hour <= 14) intensity = 0.7;   // lunch
      else if (hour >= 8 && hour <= 11) intensity = 0.55;   // morning
      else if (hour >= 15 && hour <= 17) intensity = 0.65;  // afternoon
      else if (hour >= 23 || hour <= 6) intensity = 0.1;    // night (cheap & low intent)
      // Weekend dip on weekday mornings
      if (day >= 5 && hour < 10) intensity *= 0.6;
      const visits = Math.round(intensity * 35);
      const spend = visits * (0.35 + Math.random() * 0.45);
      const cpv = visits > 0 ? spend / visits : 0;
      cells.push({ day, hour, visits, spend: Math.round(spend * 100) / 100, cpv });
    }
  }
  return cells;
}

// ────────────────────────────────────────────────────────────────
// Line Items
// ────────────────────────────────────────────────────────────────

export const mockLineItems: LineItemSummary[] = [
  {
    id: "li-001",
    campaignId: "c-001",
    brandId: "b-001",
    name: "Display + Native IT",
    status: "active",
    mode: "observation_only",
    kpi: li001Kpi,
    delta: {
      cpvDeltaPct: -0.05,
      visitsDeltaPct: 0.12,
      spendDeltaPct: -0.02,
      reachDeltaPct: 0.08,
    },
    weekLabel: "4–10 maggio",
    maxBid: 4.5,
    pacingPct: 0.88,
    breakdowns: breakdownsLi001,
    decisionsPending: 7,
  },
  {
    id: "li-002",
    campaignId: "c-001",
    brandId: "b-001",
    name: "Display IT — Retargeting",
    status: "active",
    mode: "observation_only",
    kpi: li002Kpi,
    delta: {
      cpvDeltaPct: -0.03,
      visitsDeltaPct: 0.08,
      spendDeltaPct: 0.01,
      reachDeltaPct: 0.05,
    },
    weekLabel: "4–10 maggio",
    maxBid: 3.8,
    pacingPct: 0.92,
    breakdowns: breakdownsLi001, // reuse for demo
    decisionsPending: 3,
  },
];

// ────────────────────────────────────────────────────────────────
// Campaigns (Orders)
// ────────────────────────────────────────────────────────────────

const campaignKpi: CoreKpi = {
  impressions: li001Kpi.impressions + li002Kpi.impressions,
  clicks: li001Kpi.clicks + li002Kpi.clicks,
  visits: li001Kpi.visits + li002Kpi.visits,
  spend: li001Kpi.spend + li002Kpi.spend,
  ctr: (li001Kpi.clicks + li002Kpi.clicks) / (li001Kpi.impressions + li002Kpi.impressions),
  cpv: (li001Kpi.spend + li002Kpi.spend) / (li001Kpi.visits + li002Kpi.visits),
  cpvTarget: 0.4,
  reach: 580_000,
  viewabilityRate: 0.71,
  winRate: 0.32,
  conversions: (li001Kpi.conversions ?? 0) + (li002Kpi.conversions ?? 0),
  roas: 2.65,
  frequency: 3.7,
  ntbConversions: (li001Kpi.ntbConversions ?? 0) + (li002Kpi.ntbConversions ?? 0),
};

export const mockCampaigns: CampaignSummary[] = [
  {
    id: "c-001",
    brandId: "b-001",
    name: "Q2 Display Push",
    status: "active",
    kpi: campaignKpi,
    delta: {
      cpvDeltaPct: -0.04,
      visitsDeltaPct: 0.1,
      spendDeltaPct: -0.01,
      reachDeltaPct: 0.07,
    },
    weekLabel: "4–10 maggio",
    pacingPct: 0.9,
    lineItems: mockLineItems,
    budgetTotal: 8500,
  },
];

// ────────────────────────────────────────────────────────────────
// Brand
// ────────────────────────────────────────────────────────────────

export const mockBrand: BrandSummary = {
  id: "b-001",
  name: "Brand Amico",
  status: "active",
  kpi: campaignKpi, // single campaign for now → same KPI as campaign
  delta: campaignKpi
    ? {
        cpvDeltaPct: -0.04,
        visitsDeltaPct: 0.1,
        spendDeltaPct: -0.01,
        reachDeltaPct: 0.07,
      }
    : {},
  weekLabel: "4–10 maggio",
  campaigns: mockCampaigns,
  budgetTotal: 8500,
};

// ────────────────────────────────────────────────────────────────
// Trends per level
// ────────────────────────────────────────────────────────────────

export const mockBrandTrend = brandTrend;
export const mockCampaignTrend = brandTrend;
export const mockLineItemTrend = brandTrend;

// ────────────────────────────────────────────────────────────────
// Decisions (always Line Item scoped)
// ────────────────────────────────────────────────────────────────

export const mockDecisions: DecisionRow[] = [
  { id: "d-001", lineItemId: "li-001", module: "inventory", key: "domain", value: "suspicious-clicks.example", label: "suspicious-clicks.example", previousModifier: 1.0, newModifier: 0.0, reason: "anomalous_ctr", observedCpv: null, observedVisits: 12, observedImpressions: 42000, note: "CTR 6,10% > soglia 4,00%", status: "proposed" },
  { id: "d-002", lineItemId: "li-001", module: "device", key: "device_type", value: "CTV", label: "Connected TV", previousModifier: 1.0, newModifier: 0.7, reason: "over_target", observedCpv: 11.37, observedVisits: 39, observedImpressions: 78000, note: "CPV 11,37 € vs target 0,40 € (28×), step capato a -0,30", status: "proposed" },
  { id: "d-003", lineItemId: "li-001", module: "inventory", key: "app", value: "com.twitch.android.app", label: "Twitch (com.twitch.android.app)", previousModifier: 0.85, newModifier: 0.55, reason: "over_target", observedCpv: 3.27, observedVisits: 26, observedImpressions: 38000, note: "CPV 3,27 € vs target 0,40 € (8×), step capato", status: "proposed" },
  { id: "d-004", lineItemId: "li-001", module: "device", key: "device_type", value: "MOBILE", label: "Mobile", previousModifier: 1.15, newModifier: 0.85, reason: "over_target", observedCpv: 0.59, observedVisits: 1061, observedImpressions: 520000, note: "CPV 0,59 € vs target 0,40 € (1,5×)", status: "proposed" },
  { id: "d-005", lineItemId: "li-001", module: "geo", key: "region", value: "IT-62", label: "Lazio", previousModifier: 1.0, newModifier: 0.7, reason: "over_target", observedCpv: 0.69, observedVisits: 184, observedImpressions: 105000, note: "CPV 0,69 € vs target 0,40 € (1,7×)", status: "proposed" },
  { id: "d-006", lineItemId: "li-001", module: "inventory", key: "domain", value: "repubblica.it", label: "repubblica.it", previousModifier: 1.0, newModifier: 0.7, reason: "over_target", observedCpv: 0.63, observedVisits: 242, observedImpressions: 92000, note: "CPV 0,63 € vs target 0,40 € (1,6×)", status: "proposed" },
  { id: "d-007", lineItemId: "li-001", module: "audience", key: "amazon_audience_id", value: "AUD-IM-CONNESSI", label: "In-Market: Smart Home", previousModifier: 1.0, newModifier: 1.25, reason: "under_target", observedCpv: 0.27, observedVisits: 396, observedImpressions: 110000, note: "CPV 0,27 € vs target 0,40 € (0,67×)", status: "proposed" },
];

// ────────────────────────────────────────────────────────────────
// Digest
// ────────────────────────────────────────────────────────────────

export const mockDigest = {
  weekLabel: "4–10 maggio 2026",
  generatedAt: "2026-05-11T06:02:00Z",
  text: `Questa settimana il CPV blended si è fermato a 0,60 €, ancora 50% sopra il target di 0,40 € ma in continuo miglioramento — è la sesta settimana consecutiva di calo, partendo da 0,85 € a inizio aprile. Le visite totali sono salite del 12% rispetto alla settimana scorsa, segno che il volume sta tenendo nonostante i tagli operati.

Le mosse principali proposte per questa settimana: ho azzerato il dominio suspicious-clicks.example perché il CTR è schizzato al 6,10%, ben sopra la soglia anti-bot del 4%. Connected TV resta il canale più costoso per visita (11,37 €, 28× il target) — taglio del 30% sul modifier, limitato dal passo massimo per run. Twitch in app va ridimensionato per la seconda settimana di fila, mentre l'audience "In-Market: Smart Home" emerge come il segmento più efficiente (0,27 €/visita) e merita un boost del 25%.

La prossima settimana guardo soprattutto se il boost di Smart Home regge il volume, e se Mobile risponde al taglio. Se il Lazio non rientra in target entro 14 giorni, valuto un cut più aggressivo.`,
};

// ────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────

export function getCampaignById(id: string): CampaignSummary | undefined {
  return mockCampaigns.find((c) => c.id === id);
}

export function getLineItemById(id: string): LineItemSummary | undefined {
  return mockLineItems.find((li) => li.id === id);
}

export function getDecisionsForLineItem(lineItemId: string): DecisionRow[] {
  return mockDecisions.filter((d) => d.lineItemId === lineItemId);
}
