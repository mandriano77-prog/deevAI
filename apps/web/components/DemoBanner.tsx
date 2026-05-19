"use client";

/**
 * DemoBanner — sticky amber strip rendered above the app shell when the
 * authenticated tenant has `tenant_is_demo === true` on /v1/auth/me.
 *
 * We deliberately fetch /auth/me from the client (and not from a server
 * component) so the banner shows even on routes that already pre-fetch
 * their own data — the banner is a global, cross-page concern.
 *
 * Failure modes are silent: if the API is unreachable or returns an error,
 * we simply render nothing. Real users with no token never see this.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiFetch, ApiError } from "@/lib/api";

interface MeResponse {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  tenant_id: string;
  tenant_slug: string;
  tenant_name: string;
  tenant_is_demo?: boolean;
}

export function DemoBanner() {
  const [isDemo, setIsDemo] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await apiFetch<MeResponse>("/auth/me");
        if (!cancelled) setIsDemo(Boolean(me.tenant_is_demo));
      } catch (err) {
        // Not logged in or API offline — banner stays hidden.
        if (!(err instanceof ApiError)) {
          // eslint-disable-next-line no-console
          console.debug("[DemoBanner] /auth/me failed", err);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!isDemo) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="sticky top-0 z-50 flex items-center justify-between gap-3 border-b border-amber-700/40 bg-amber-500/10 px-6 py-2 text-xs text-amber-200 backdrop-blur"
    >
      <div className="flex items-center gap-2">
        <span aria-hidden className="text-base leading-none">🎭</span>
        <span>
          Stai navigando l&apos;account demo. Le modifiche sono disabilitate.
        </span>
      </div>
      <Link
        href="/signup"
        className="rounded-md border border-amber-400/60 px-3 py-1 text-amber-100 transition hover:border-amber-300 hover:text-amber-50"
      >
        Connetti il tuo DV360 →
      </Link>
    </div>
  );
}
