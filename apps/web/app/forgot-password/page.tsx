"use client";

import Link from "next/link";
import { useState } from "react";

import { Wordmark } from "@/components/wordmark";
import { ApiError, auth } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await auth.forgotPassword(email);
      setSent(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError("Richiesta non riuscita. Riprova tra poco.");
      } else {
        setError("Errore di connessione");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-900 px-6">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Wordmark variant="logo" className="text-3xl" />
          <p className="text-sm text-ink-400">Reimposta la password</p>
        </div>

        {sent ? (
          <div className="space-y-4 rounded-lg border border-ink-800 bg-ink-900 px-5 py-6 text-sm text-ink-200">
            <p>
              Se l&apos;indirizzo è registrato, riceverai un&apos;email con un link
              valido per un&apos;ora.
            </p>
            <p className="text-xs text-ink-400">Controlla anche la cartella spam.</p>
            <Link
              href="/login"
              className="inline-block text-accent-400 hover:text-accent-300"
            >
              Torna al login
            </Link>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-ink-200">
                Email
              </span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent-400 focus:outline-none"
                placeholder="mario@brand.it"
              />
            </label>

            {error ? (
              <div className="rounded-md border border-red-900 bg-red-900/30 px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-md bg-accent-600 px-4 py-2.5 text-sm font-medium text-ink-50 transition hover:bg-accent-700 disabled:opacity-60"
            >
              {loading ? "Invio..." : "Invia link di reset"}
            </button>

            <p className="text-center text-xs text-ink-400">
              <Link href="/login" className="text-accent-400 hover:text-accent-300">
                Torna al login
              </Link>
            </p>
          </form>
        )}
      </div>
    </main>
  );
}
