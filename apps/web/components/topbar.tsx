"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  integrations,
  lineItems,
  runs,
  tenants,
  type IntegrationRead,
  type LineItemRead,
} from "@/lib/api";

interface TopbarProps {
  title: string;
  subtitle?: string;
  lineItems?: LineItemRead[];
  onRunComplete?: () => void;
}

export function Topbar({
  title,
  subtitle,
  lineItems: lineItemsProp,
  onRunComplete,
}: TopbarProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-ink-800 bg-ink-900 px-6">
      <div>
        <h1 className="text-base font-medium text-ink-50">{title}</h1>
        {subtitle ? <p className="text-xs text-ink-400">{subtitle}</p> : null}
      </div>

      <div className="flex items-center gap-4">
        <ContextSelector lineItems={lineItemsProp} />
        <TriggerRunButton
          lineItems={lineItemsProp}
          onRunComplete={onRunComplete}
        />
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-ink-800 text-xs font-medium text-ink-200">
          A
        </div>
      </div>
    </header>
  );
}

function TriggerRunButton({
  lineItems: lineItemsProp,
  onRunComplete,
}: {
  lineItems?: LineItemRead[];
  onRunComplete?: () => void;
}) {
  const [items, setItems] = useState<LineItemRead[]>(lineItemsProp ?? []);
  const [triggering, setTriggering] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (lineItemsProp) {
      setItems(lineItemsProp);
      return;
    }
    void lineItems.list().then(setItems).catch(() => setItems([]));
  }, [lineItemsProp]);

  const handleTrigger = async () => {
    const lineItemId = items[0]?.id;
    if (!lineItemId) {
      setMessage("Configura un line item prima di avviare un run.");
      return;
    }
    setTriggering(true);
    setMessage(null);
    try {
      await runs.trigger({ line_item_id: lineItemId, language: "it" });
      setMessage("Run avviato.");
      onRunComplete?.();
    } catch (e) {
      setMessage(
        e instanceof ApiError ? `Errore (${e.status})` : "Run non riuscito",
      );
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        disabled={triggering || items.length === 0}
        onClick={() => void handleTrigger()}
        className="rounded-md bg-accent-600 px-3 py-1.5 text-xs font-medium text-ink-50 hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {triggering ? "Avvio…" : "Avvia nuovo run"}
      </button>
      {message ? (
        <span className="text-[10px] text-ink-400">{message}</span>
      ) : null}
    </div>
  );
}

function ContextSelector({
  lineItems: lineItemsProp,
}: {
  lineItems?: LineItemRead[];
}) {
  const [open, setOpen] = useState(false);
  const [tenantName, setTenantName] = useState("Workspace");
  const [integrationList, setIntegrationList] = useState<IntegrationRead[]>([]);
  const [items, setItems] = useState<LineItemRead[]>(lineItemsProp ?? []);

  const load = useCallback(async () => {
    try {
      const [me, ints, lis] = await Promise.all([
        tenants.me(),
        integrations.list(),
        lineItemsProp ? Promise.resolve(lineItemsProp) : lineItems.list(),
      ]);
      setTenantName(me.name);
      setIntegrationList(ints);
      setItems(lis);
    } catch {
      /* keep defaults */
    }
  }, [lineItemsProp]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-md border border-ink-700 px-3 py-1.5 text-xs text-ink-200 hover:border-ink-500 hover:text-ink-50"
      >
        <span className="text-ink-50">{tenantName}</span>
        <span className="ml-1 text-ink-400">▾</span>
      </button>

      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border border-ink-700 bg-ink-900 p-2 shadow-xl">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-ink-400">
            Brand
          </div>
          <Link
            href="/dashboard"
            className="block rounded-md px-3 py-2 text-sm text-ink-100 hover:bg-ink-800"
            onClick={() => setOpen(false)}
          >
            {tenantName}
          </Link>

          <div className="mt-2 px-3 py-2 text-[10px] uppercase tracking-wider text-ink-400">
            Integrazioni
          </div>
          {integrationList.length === 0 ? (
            <p className="px-3 py-2 text-xs text-ink-500">Nessuna integrazione</p>
          ) : (
            integrationList.map((i) => (
              <div
                key={i.id}
                className="rounded-md px-3 py-2 text-sm text-ink-200"
              >
                <div className="font-medium">{i.name}</div>
                <div className="text-xs text-ink-400">{i.status}</div>
              </div>
            ))
          )}

          <div className="mt-2 px-3 py-2 text-[10px] uppercase tracking-wider text-ink-400">
            Line item
          </div>
          {items.length === 0 ? (
            <p className="px-3 py-2 text-xs text-ink-500">Nessun line item</p>
          ) : (
            items.map((li) => (
              <Link
                key={li.id}
                href={`/line-item/${li.id}`}
                className="block rounded-md px-3 py-2 text-sm text-ink-200 hover:bg-ink-800"
                onClick={() => setOpen(false)}
              >
                <div className="font-medium">{li.name}</div>
                <div className="text-xs text-ink-400">
                  CPV target {li.cpv_target.toFixed(2)} € · {li.mode}
                </div>
              </Link>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
