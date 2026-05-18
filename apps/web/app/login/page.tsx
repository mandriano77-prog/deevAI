"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Wordmark } from "@/components/wordmark";
import { ApiError, auth } from "@/lib/api";
import { setStoredToken } from "@/lib/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const resp = await auth.login({ email, password });
      setStoredToken(resp.access_token, resp.tenant_slug);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = (err.detail as { detail?: string })?.detail;
        setError(typeof detail === "string" ? detail : `Errore ${err.status}`);
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
          <p className="text-sm text-ink-400">Accedi al tuo workspace</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-200">Email</span>
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

          <label className="block">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium text-ink-200">Password</span>
              <Link
                href="/forgot-password"
                className="text-xs text-accent-400 hover:text-accent-300"
              >
                Password dimenticata?
              </Link>
            </div>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent-400 focus:outline-none"
              placeholder="••••••••"
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
            {loading ? "Accedo..." : "Accedi"}
          </button>

          <p className="text-center text-xs text-ink-400">
            Non hai un account?{" "}
            <Link href="/signup" className="text-accent-400 hover:text-accent-300">
              Crea workspace
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
