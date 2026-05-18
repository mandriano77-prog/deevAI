# Multi-Provider Refactor — Design Doc

> **Status:** Draft v1 (2026-05-17)
> **Owner:** Adriano
> **Goal:** Extend deevAI to support **DV360** and **The Trade Desk** in addition to **Amazon DSP**, without forking the codebase.
> **Non-goal:** Implementing DV360/TTD clients in this phase. This doc covers the architectural refactor that makes them addable as a localized effort.

---

## 1. Why now

deevAI works on Amazon DSP today. Two strategic reasons to go multi-provider:

1. **TAM expansion** — Amazon DSP is a fraction of the programmatic spend in EU. DV360 alone is 4-5× larger by volume; TTD has the premium / CTV segment.
2. **De-risking** — Single-provider products live or die by one API. Multi-provider gives a fallback narrative for sales and for engineering.

The codebase already hints at this future (`provider: str` column on `Integration`, separated `packages/bidagent/amazon/` subpackage, decision engine that is platform-agnostic). The refactor formalizes that intent.

---

## 2. Current state assessment

### 2.1 What's already provider-agnostic ✅
- **Decision engine** (`packages/bidagent/decision_engine.py`) — pure functions. Input: `list[TermMetric]` + `list[ModifierTerm]` + `OptimizerConfig`. Output: `Plan`. Zero Amazon imports.
- **Multi-objective scorer** (`packages/bidagent/multi_objective.py`) — same: works on canonical `TermMetric`.
- **Digest generator** (`packages/bidagent/digest_generator.py`) — narrates a `Plan`. Provider-blind.
- **Core data classes** (`packages/bidagent/models.py`) — `TermMetric`, `ModifierTerm`, `Plan` use canonical fields (`targeting_module`, `targeting_key`, `value`).

### 2.2 Where Amazon is leaked ⚠️
Audit: **42/135 Python files** mention `amazon` / `amc` / `dsp`.

| Layer | File(s) | Leak type |
|-------|---------|-----------|
| **bidagent** | `amazon/auth.py`, `amazon/amc_client.py`, `amazon/dsp_client.py`, `amazon/mock_data.py` | ✅ Already isolated in subpackage — good. Just needs a base interface above it. |
| **bidagent** | `__main__.py` | Imports `amazon.*` directly. Needs provider switch. |
| **bidagent** | `mock_data.py` (root, not amazon/) | Beeswax-shaped mock — fine, decouples engine from any real provider. |
| **API models** | `integration.py` | Columns: `amazon_entity_id`, `amazon_profile_id`, `amazon_region`, `amazon_marketplace_id`, `amc_instance_id`. **Provider-specific schema.** |
| **API models** | `line_item.py` | Columns with `amazon_*` prefix (DSP rule IDs from migration `0002`). |
| **API models** | `tenant.py`, `advertiser.py`, `decision.py` | Light mentions in docstrings/comments. |
| **API services** | `amazon_oauth.py`, `amazon_profiles.py`, `dsp_apply.py` | Pure Amazon logic. Need to be moved under `services/providers/amazon/`. |
| **API services** | `bidagent_runtime.py`, `scheduler.py`, `dsp_apply.py` | Orchestration hard-wired to Amazon. |
| **API routers** | `integrations.py`, `runs.py`, `digests.py`, `line_items.py`, `advertisers.py` | OAuth flow, runs, digests, line items have Amazon-specific code paths. |
| **Migrations** | `0001_initial.py`, `0002_line_item_dsp_rule_ids.py` | Schema includes Amazon-shaped columns. Backward compatibility required. |

### 2.3 Provider concept differences

| Concept | Amazon DSP | DV360 | The Trade Desk |
|---------|-----------|-------|----------------|
| **Hierarchy** | Advertiser → Order → Line Item → Ad Group | Partner → Advertiser → Campaign → IO → Line Item | Partner → Advertiser → Campaign → Ad Group |
| **Bid adjustments** | Rules API → Ad Group | Native on Line Item, or Custom Bidding Script (JS) | Bid Lists + Custom Bidding Algorithms |
| **Metrics source** | AMC (SQL clean room, async, 24-48h latency) | DV360 Reporting API (sync, ~3h) or Ads Data Hub | TTD Reporting API (REST, 1-3h) |
| **Auth** | LWA OAuth + per-profile token | Google OAuth + GCP service account | Partner OAuth, long-lived token |
| **Conversion source** | AMC events | Floodlight | UPixel / Tracking Tags |
| **Targeting dimensions** | domain, app, deviceType, geo, behavioralSegment | site, app, device, geo, audience, contextual | site, app, device, country/region, audience, contextual |
| **Application semantic** | Write a "rule" with N terms, associate to ad group | PATCH line item OR upload Custom Bidding script | Write a Bid List or push a CBA |

Implications:
- Each provider needs **its own auth client**, **metrics reader**, **bid writer**.
- Each provider has its own **targeting dimension vocabulary**, which must map to/from a canonical internal vocabulary.
- The **scheduler / runtime** must understand provider-specific latency (Amazon AMC needs longer windows than TTD).

---

## 3. Target architecture

### 3.1 Layering

```
┌───────────────────────────────────────────────────────────────┐
│  apps/web (Next.js)                                            │
│  - Provider-aware OAuth flow per integration                  │
│  - Same dashboards, run history, digest UI                    │
└───────────────────────────────────────────────────────────────┘
                              │ HTTP
┌──────────────────────────────▼────────────────────────────────┐
│  apps/api (FastAPI)                                           │
│  Provider-agnostic routers + service layer                    │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  services/providers/registry.py                        │   │
│  │  - get_metrics_provider(integration) → MetricsProvider │   │
│  │  - get_bid_provider(integration)     → BidProvider     │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  services/providers/amazon/   (existing, relocated)    │   │
│  │  services/providers/dv360/    (future)                 │   │
│  │  services/providers/ttd/      (future)                 │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬────────────────────────────────┘
                              │ Python calls
┌──────────────────────────────▼────────────────────────────────┐
│  packages/bidagent (pure engine)                              │
│  - decision_engine.py   (already provider-agnostic) ✅        │
│  - multi_objective.py   (already provider-agnostic) ✅        │
│  - digest_generator.py  (already provider-agnostic) ✅        │
│  - models.py            (canonical data classes)    ✅        │
│  - providers/base.py    (NEW: abstract interfaces)            │
│  - providers/amazon/    (relocated from bidagent/amazon/)     │
│  - providers/dv360/     (future)                              │
│  - providers/ttd/       (future)                              │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 Provider interface (proposed)

```python
# packages/bidagent/providers/base.py
from abc import ABC, abstractmethod
from datetime import date
from ..models import TermMetric, ModifierTerm, Plan

class ProviderCredentials(ABC):
    """Opaque bag of credentials. Each provider subclasses."""

class MetricsProvider(ABC):
    """Reads observed performance for a line item over a window."""

    @abstractmethod
    def fetch_week_metrics(
        self,
        line_item_external_id: str,
        week_start: date,
        week_end: date,
    ) -> list[TermMetric]:
        ...

class BidProvider(ABC):
    """Reads & writes current bid modifiers."""

    @abstractmethod
    def get_current_modifiers(
        self,
        line_item_external_id: str,
    ) -> list[ModifierTerm]:
        ...

    @abstractmethod
    def apply_plan(
        self,
        plan: Plan,
        dry_run: bool = True,
    ) -> "ApplyResult":
        ...
```

Each implementation translates canonical `TermMetric` / `ModifierTerm` ↔ provider-specific payload. The decision engine never sees a provider-specific shape.

### 3.3 DB schema changes (minimal & reversible)

The current `Integration` table has Amazon-specific columns. Two strategies:

**Option A — JSONB blob (preferred)**
- Add `provider_config: JSONB` column.
- Backfill by moving `amazon_entity_id`, `amazon_profile_id`, `amazon_region`, `amazon_marketplace_id`, `amc_instance_id` into the JSON.
- Keep old columns as nullable for one release, drop in next migration.

**Option B — Per-provider table**
- `IntegrationAmazon`, `IntegrationDv360`, `IntegrationTtd` joined by `integration_id`.
- More normalized, more tables, more queries.

**Recommendation: Option A.** Less ceremony, matches the "one Integration row per (tenant, provider)" model that's already in place.

Equivalent treatment for `LineItem.amazon_*` columns → `LineItem.platform_metadata: JSONB`.

### 3.4 Canonical targeting vocabulary

Already exists in `bidagent/models.py` via `TermMetric.targeting_module / targeting_key`. We formalize:

| Canonical key | Amazon DSP | DV360 | TTD |
|---------------|------------|-------|-----|
| `inventory.domain` | `domain` | `site` | `site` |
| `inventory.app` | `appId` | `app` | `app` |
| `device.type` | `deviceType` | `device` | `device_type` |
| `geo.country` | `country` | `country` | `country` |
| `geo.region` | `region` | `region` | `region` |
| `geo.city` | `city` | `city` | `city` |
| `audience.id` | `behavioralSegment` | `audience` | `audience` |

Provider modules implement `to_provider(canonical) → provider_shape` and `from_provider(provider_shape) → canonical`.

---

## 4. Migration plan (phased, reversible)

### Phase 1 — Internal refactor only (no behaviour change)
Estimated: **1 week with AI assistance, 2-3 weeks solo.**

1. Create `packages/bidagent/providers/base.py` with `MetricsProvider`, `BidProvider` ABCs.
2. Move `packages/bidagent/amazon/` → `packages/bidagent/providers/amazon/`.
3. Implement `MetricsProvider` and `BidProvider` for Amazon (wrapping existing code).
4. Update `bidagent/__main__.py` to use the provider registry.
5. Create `apps/api/deevai_api/services/providers/` mirror.
6. Move `services/amazon_oauth.py`, `services/amazon_profiles.py`, `services/dsp_apply.py` → `services/providers/amazon/`.
7. Build `services/providers/registry.py` with provider lookup by `Integration.provider`.
8. Add `provider_config: JSONB` column on `Integration` + `platform_metadata: JSONB` on `LineItem`. Migration `0011_provider_config.py`. Backfill from Amazon columns. **Keep old columns** as nullable for one release.

**Acceptance:** all existing tests pass, Amazon flow unchanged from user POV, no DB downtime.

### Phase 2 — DV360 provider
Estimated: **1.5-2 weeks with AI assistance.**

1. Implement `packages/bidagent/providers/dv360/` (`auth`, `metrics_client`, `bid_client`, `mock_data`).
2. Implement `apps/api/deevai_api/services/providers/dv360/` (OAuth flow, profile selection).
3. Add `mock-dv360` CLI command, mirror of `demo-amazon`.
4. Update FE: add "Connect DV360" button on the integrations page.
5. Document differences in `docs/PROVIDERS.md`.

**Acceptance:** demo run on mock DV360 data produces a valid `Plan`, applied dry-run, digest reads correctly.

### Phase 3 — The Trade Desk provider
Estimated: **1.5-2 weeks with AI assistance.**

Same structure as Phase 2.

### Phase 4 — Cleanup & polish
- Drop deprecated `amazon_*` columns once Phase 1 is in prod for 1+ release.
- Add provider filter to dashboards.
- Pricing/billing per-provider (separate doc).
- Marketing: 3 landing pages (one per provider).

---

## 5. Risks & open questions

### Risks
- **AMC vs Reporting API mismatch.** AMC is async + clean room; DV360 Reporting API is sync + grain-limited. The runtime / scheduler must handle both. Mitigation: make `fetch_week_metrics` async-by-default; Amazon implementation polls, DV360 returns immediately.
- **Custom Bidding Scripts (DV360).** Generating JS bidding scripts is a different problem from emitting bid adjustment rules. Decision: in v1 we **only use native bid adjustments** for DV360; Custom Bidding Scripts become a Phase 5+ feature.
- **TTD partner credentials.** TTD requires a partner-level seat. Onboarding friction is higher than Amazon/DV360. May affect sales motion.
- **Targeting dimension coverage gaps.** Some dimensions exist on one platform and not the others (e.g., `behavioralSegment` is Amazon-only naming). Mitigation: canonical vocabulary, provider-specific fallback to "unsupported on this provider" with a clear UI hint.

### Open questions
1. **Pricing model:** flat per-tenant or per-platform? My recommendation: per-platform (it's how AppLovin / Skai / Aki price).
2. **Branding:** is "deevAI" tied to Amazon's "Manaus" pun? Multi-provider might want a more neutral umbrella name (e.g., "MAi by [Brand]"). Defer to marketing.
3. **Order of execution:** DV360 first or TTD first?
   - Recommendation: **DV360 first.** Bigger TAM, mature API, easier sales motion.

---

## 6. Success criteria

A tenant can:
1. Connect an Amazon DSP integration (today's flow, unchanged).
2. **Or** connect a DV360 integration (new).
3. **Or** connect a TTD integration (new).
4. Run weekly optimization on any of the above with the same UX, same digest, same approval flow.
5. The codebase has **zero hard-coded references to "amazon" / "dsp" / "amc"** outside `providers/amazon/`.

---

## 7. What to read next

- `packages/bidagent/decision_engine.py` — the unchanged core.
- `packages/bidagent/models.py` — canonical data classes.
- `packages/bidagent/amazon/dsp_client.py` — reference implementation that providers/dv360 and providers/ttd will mirror.
- `apps/api/deevai_api/models/integration.py` — current schema, Amazon-shaped today.
- `docs/CURSOR_BRIEF.md` — product context, metric-agnostic strategy that this refactor inherits cleanly.
