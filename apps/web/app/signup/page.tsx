"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Wordmark } from "@/components/wordmark";
import { auth, ApiError } from "@/lib/api";
import { setStoredToken } from "@/lib/auth-store";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    email: "",
    password: "",
    tenant_name: "",
    tenant_slug: "",
    full_name: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function field(name: keyof typeof form) {
    return {
      value: form[name],
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm({ ...form, [name]: e.target.value }),
    };
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const resp = await auth.signup(form);
      setStoredToken(resp.access_token, resp.tenant_slug);
      router.push("/onboarding");
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
          <p className="text-sm text-ink-400">
            Crea il tuo account · 14 giorni di observation only inclusi
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Field label="Nome">
            <input
              type="text"
              required
              autoComplete="name"
              {...field("full_name")}
              className={inputCls}
              placeholder="Mario Rossi"
            />
          </Field>

          <Field label="Email aziendale">
            <input
              type="email"
              required
              autoComplete="email"
              {...field("email")}
              className={inputCls}
              placeholder="mario@brand.it"
            />
          </Field>

          <Field label="Password" hint="Almeno 8 caratteri">
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              {...field("password")}
              className={inputCls}
              placeholder="••••••••"
            />
          </Field>

          <Field label="Nome del tuo workspace">
            <input
              type="text"
              required
              {...field("tenant_name")}
              className={inputCls}
              placeholder="Brand Amico"
            />
          </Field>

          <Field
            label="Slug del workspace"
            hint="solo minuscole, numeri, trattini · sarà nell'URL"
          >
            <input
              type="text"
              required
              pattern="[a-z0-9][a-z0-9-]*"
              {...field("tenant_slug")}
              className={inputCls}
              placeholder="brand-amico"
            />
          </Field>

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
            {loading ? "Creo account..." : "Crea account"}
          </button>

          <p className="text-center text-xs text-ink-400">
            Dopo la registrazione riceverai un&apos;email di benvenuto con il link
            alla dashboard.
          </p>
          <p className="text-center text-xs text-ink-400">
            Hai già un account?{" "}
            <Link href="/login" className="text-accent-400 hover:text-accent-300">
              Accedi
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}

const inputCls =
  "w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-500 focus:border-accent-400 focus:outline-none";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-200">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-ink-500">{hint}</span> : null}
    </label>
  );
}
