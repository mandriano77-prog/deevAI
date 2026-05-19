"use client";

/**
 * TryDemoButton — landing-page CTA that one-clicks into the demo tenant.
 *
 * Flow:
 *   1. POST /auth/demo-login (no body) → TokenResponse
 *   2. Persist token + tenant slug in localStorage (same path as login)
 *   3. Redirect to /dashboard so the prospect lands in the product UI
 *
 * If the backend is not configured for demo mode (DEMO_TENANT_ID unset →
 * 404), we surface a friendly "demo non disponibile" message and link to
 * /signup as the fallback path. Other errors fall back to a generic copy.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, auth } from "@/lib/api";
import { setStoredToken } from "@/lib/auth-store";

interface Props {
  className?: string;
  variant?: "primary" | "secondary";
}

export function TryDemoButton({ className = "", variant = "primary" }: Props) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setError(null);
    setLoading(true);
    try {
      const token = await auth.demoLogin();
      setStoredToken(token.access_token, token.tenant_slug);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Demo non ancora attivo su questo ambiente.");
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Troppi tentativi dal tuo IP. Riprova tra un'ora.");
      } else {
        setError("Errore nel caricamento del demo. Riprova fra poco.");
      }
      setLoading(false);
    }
  };

  const base =
    variant === "primary"
      ? "rounded-md bg-accent-600 px-5 py-2.5 text-sm font-medium text-ink-50 transition hover:bg-accent-700 disabled:opacity-60 disabled:cursor-not-allowed"
      : "rounded-md border border-ink-600 px-5 py-2.5 text-sm font-medium text-ink-100 transition hover:border-accent-400 hover:text-accent-300 disabled:opacity-60 disabled:cursor-not-allowed";

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={loading}
        className={`${base} ${className}`.trim()}
      >
        {loading ? "Apertura demo…" : "Prova la demo →"}
      </button>
      {error ? (
        <p className="text-xs text-amber-300" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
