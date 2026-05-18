"use client";

import { useState } from "react";

import {
  advertisers,
  ApiError,
  lineItems,
  type IntegrationRead,
} from "@/lib/api";

interface LineItemSetupProps {
  integrations: IntegrationRead[];
  onCreated: () => void;
}

export function LineItemSetup({ integrations, onCreated }: LineItemSetupProps) {
  const connected = integrations.filter((i) => i.status === "connected");
  const [integrationId, setIntegrationId] = useState(connected[0]?.id ?? "");
  const [advertiserId, setAdvertiserId] = useState("");
  const [advertiserName, setAdvertiserName] = useState("");
  const [lineItemName, setLineItemName] = useState("");
  const [lineItemId, setLineItemId] = useState("");
  const [adGroupId, setAdGroupId] = useState("");
  const [cpvTarget, setCpvTarget] = useState("0.40");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (connected.length === 0) {
    return (
      <p className="mt-4 text-sm text-ink-400">
        Collega prima la DSP in onboarding, poi torna qui per registrare il line
        item.
      </p>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const adv = await advertisers.create({
        integration_id: integrationId,
        amazon_advertiser_id: advertiserId.trim(),
        name: advertiserName.trim() || `Advertiser ${advertiserId.trim()}`,
      });
      await lineItems.create({
        advertiser_id: adv.id,
        name: lineItemName.trim(),
        amazon_line_item_id: lineItemId.trim(),
        amazon_ad_group_id: adGroupId.trim() || undefined,
        cpv_target: parseFloat(cpvTarget),
      });
      onCreated();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `Errore API (${err.status})`
          : "Impossibile salvare il line item",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mx-auto mt-6 max-w-lg space-y-4 text-left">
      <label className="block text-xs text-ink-400">
        Integrazione
        <select
          value={integrationId}
          onChange={(e) => setIntegrationId(e.target.value)}
          className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
          required
        >
          {connected.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name} ({i.provider})
            </option>
          ))}
        </select>
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-xs text-ink-400">
          DSP Advertiser ID
          <input
            value={advertiserId}
            onChange={(e) => setAdvertiserId(e.target.value)}
            placeholder="Amazon-Ads-AccountId"
            className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
            required
          />
        </label>
        <label className="block text-xs text-ink-400">
          Nome advertiser
          <input
            value={advertiserName}
            onChange={(e) => setAdvertiserName(e.target.value)}
            placeholder="Brand"
            className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
          />
        </label>
      </div>

      <label className="block text-xs text-ink-400">
        Nome line item
        <input
          value={lineItemName}
          onChange={(e) => setLineItemName(e.target.value)}
          className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
          required
        />
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-xs text-ink-400">
          Line item ID (DSP)
          <input
            value={lineItemId}
            onChange={(e) => setLineItemId(e.target.value)}
            className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
            required
          />
        </label>
        <label className="block text-xs text-ink-400">
          Ad group ID
          <input
            value={adGroupId}
            onChange={(e) => setAdGroupId(e.target.value)}
            placeholder="se vuoto = line item ID"
            className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
          />
        </label>
      </div>

      <label className="block text-xs text-ink-400">
        Target CPV (€)
        <input
          type="number"
          step="0.01"
          min="0.01"
          value={cpvTarget}
          onChange={(e) => setCpvTarget(e.target.value)}
          className="mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50"
          required
        />
      </label>

      {error ? <p className="text-sm text-red-300">{error}</p> : null}

      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-ink-50 hover:bg-accent-700 disabled:opacity-50"
      >
        {loading ? "Salvataggio…" : "Registra line item"}
      </button>

      <p className="text-xs text-ink-500">
        Gli ID li trovi nella console DSP. L&apos;ad group è quello usato dalle
        bid adjustment rules Amazon.
      </p>
    </form>
  );
}
