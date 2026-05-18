"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Wordmark } from "@/components/wordmark";
import { ApiError, auth } from "@/lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Le password non coincidono");
      return;
    }
    if (!token) {
      setError("Link non valido — richiedi un nuovo reset dalla pagina login");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await auth.resetPassword({ token, password });
      setDone(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = (err.detail as { detail?: string })?.detail;
        setError(
          typeof detail === "string" ? detail : "Link non valido o scaduto",
        );
      } else {
        setError("Errore di connessione");
      }
    } finally {
      setLoading(false);
    }
  }

  if (!token && !done) {
    return (
      <div className="space-y-4 text-sm text-ink-200">
        <p>Link mancante o non valido.</p>
        <Link href="/forgot-password" className="text-accent-400 hover:text-accent-300">
          Richiedi un nuovo link
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="space-y-3 text-sm text-ink-200">
        <p>Password aggiornata. Reindirizzamento al login…</p>
        <Link href="/login" className="text-accent-400 hover:text-accent-300">
          Vai al login
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ink-200">
          Nuova password
        </span>
        <input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-100 focus:border-accent-400 focus:outline-none"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ink-200">
          Conferma password
        </span>
        <input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-100 focus:border-accent-400 focus:outline-none"
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
        className="w-full rounded-md bg-accent-600 px-4 py-2.5 text-sm font-medium text-ink-50 hover:bg-accent-700 disabled:opacity-60"
      >
        {loading ? "Salvo..." : "Imposta nuova password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-900 px-6">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Wordmark variant="logo" className="text-3xl" />
          <p className="text-sm text-ink-400">Nuova password</p>
        </div>
        <Suspense fallback={<p className="text-sm text-ink-400">Caricamento…</p>}>
          <ResetPasswordForm />
        </Suspense>
        <p className="mt-6 text-center text-xs text-ink-400">
          <Link href="/login" className="text-accent-400 hover:text-accent-300">
            Torna al login
          </Link>
        </p>
      </div>
    </main>
  );
}
