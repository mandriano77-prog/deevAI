"use client";

import { useEffect, useState } from "react";

import { lineItems } from "@/lib/api";

const ENV_LINE_ITEM_ID = process.env.NEXT_PUBLIC_MAI_LINE_ITEM_ID ?? "";

/** Active line item for M.AI — env override, else first tenant line item. */
export function useMaiLineItemId(): { lineItemId: string; loading: boolean; error: string | null } {
  const [lineItemId, setLineItemId] = useState(ENV_LINE_ITEM_ID);
  const [loading, setLoading] = useState(!ENV_LINE_ITEM_ID);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ENV_LINE_ITEM_ID) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    void lineItems
      .list()
      .then((items) => {
        if (cancelled) return;
        if (items.length > 0) {
          setLineItemId(items[0].id);
          setError(null);
        } else {
          setError("Nessun line item collegato. Completa l'onboarding.");
        }
      })
      .catch(() => {
        if (!cancelled) setError("Impossibile caricare i line item.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { lineItemId, loading, error };
}
