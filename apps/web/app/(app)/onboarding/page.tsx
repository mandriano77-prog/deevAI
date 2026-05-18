"use client";

/**
 * DeevAI onboarding — DV360 OAuth user-consent flow.
 *
 * Four steps:
 *   1) Intro / requirements (Google Cloud OAuth client setup)
 *   2) Connect form  → POST /integrations/dv360/connect, redirect to Google
 *   3) Callback handling (auto when ?code & ?state are in the URL)
 *   4) Pick the advertiser from the list returned by the callback
 *
 * Google redirects the browser back to THIS page (the redirect_uri
 * configured server-side is `…/onboarding`). On mount we look at the
 * query string; if `code` is present we forward to the backend and
 * jump to the advertiser picker.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import {
  ApiError,
  type Dv360AdvertiserRead,
  type Dv360ConnectBody,
  integrations,
} from "@/lib/api";

type Step = "intro" | "connect" | "exchanging" | "advertiser";

interface FormState extends Dv360ConnectBody {}

// Next 15 requires `useSearchParams()` to live under a Suspense boundary,
// otherwise the whole page bails out of static prerendering and the build
// fails. We wrap the real component in a thin Suspense shell so the page
// itself stays prerenderable.
export default function Dv360OnboardingPage() {
  return (
    <Suspense fallback={<PageShellLoader />}>
      <Dv360OnboardingInner />
    </Suspense>
  );
}

function PageShellLoader() {
  return (
    <div className="min-h-screen bg-ink-900 px-6 py-12">
      <div className="mx-auto max-w-2xl text-center text-sm text-ink-400">
        Carico…
      </div>
    </div>
  );
}

function Dv360OnboardingInner() {
  const router = useRouter();
  const params = useSearchParams();

  const [step, setStep] = useState<Step>("intro");
  const [form, setForm] = useState<FormState>({
    name: "DV360",
    client_id: "",
    client_secret: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [integrationId, setIntegrationId] = useState<string | null>(null);
  const [advertisers, setAdvertisers] = useState<Dv360AdvertiserRead[]>([]);
  const [chosenAdvertiserId, setChosenAdvertiserId] = useState<string | null>(
    null,
  );

  // ── On mount: if Google just redirected back, handle the callback ──
  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const oauthError = params.get("error");

    if (oauthError) {
      setError(`Consenso negato su Google: ${oauthError}`);
      setStep("connect");
      return;
    }
    if (code && state) {
      setStep("exchanging");
      (async () => {
        try {
          const result = await integrations.dv360Callback(code, state);
          setIntegrationId(result.integration_id);
          setAdvertisers(result.advertisers);
          setStep("advertiser");
          // Clean the URL so reloading doesn't re-trigger the exchange.
          router.replace("/onboarding/dv360");
        } catch (err) {
          setError(formatError(err));
          setStep("connect");
        }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onConnect(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const resp = await integrations.connectDv360(form);
      window.location.href = resp.authorize_url;
    } catch (err) {
      setError(formatError(err));
      setLoading(false);
    }
  }

  async function onPickAdvertiser() {
    if (!integrationId || !chosenAdvertiserId) return;
    setLoading(true);
    setError(null);
    try {
      const adv = advertisers.find(
        (a) => a.advertiser_id === chosenAdvertiserId,
      );
      await integrations.selectDv360Advertiser(integrationId, {
        advertiser_id: chosenAdvertiserId,
        partner_id: adv?.partner_id ?? undefined,
      });
      router.push("/dashboard");
    } catch (err) {
      setError(formatError(err));
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-ink-900 px-6 py-12">
      <div className="mx-auto max-w-2xl">
        <StepIndicator step={step} />

        {step === "intro" ? (
          <IntroStep onNext={() => setStep("connect")} />
        ) : step === "connect" ? (
          <ConnectStep
            form={form}
            setForm={setForm}
            onSubmit={onConnect}
            onBack={() => setStep("intro")}
            loading={loading}
            error={error}
          />
        ) : step === "exchanging" ? (
          <ExchangingStep />
        ) : (
          <AdvertiserStep
            advertisers={advertisers}
            chosen={chosenAdvertiserId}
            onPick={setChosenAdvertiserId}
            onConfirm={onPickAdvertiser}
            loading={loading}
            error={error}
          />
        )}
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    const raw = err.detail;
    if (typeof raw === "string") return raw;
    if (raw && typeof raw === "object" && "detail" in raw) {
      const d = (raw as { detail?: unknown }).detail;
      if (typeof d === "string") return d;
    }
    return `Errore API ${err.status}`;
  }
  if (err instanceof Error) return err.message || "Errore di connessione";
  return "Errore di connessione";
}

// ───────────────────────────────────────────────────────────────────────────
// UI fragments
// ───────────────────────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: Step }) {
  const order: Step[] = ["intro", "connect", "exchanging", "advertiser"];
  const reached = (s: Step) => order.indexOf(s) <= order.indexOf(step);
  const items: { id: Step; n: number; label: string }[] = [
    { id: "intro", n: 1, label: "Cosa serve" },
    { id: "connect", n: 2, label: "Connetti DV360" },
    { id: "advertiser", n: 3, label: "Scegli advertiser" },
  ];
  return (
    <ol className="mb-12 flex items-center justify-center gap-6 text-xs">
      {items.map((it, i) => (
        <li key={it.id} className="flex items-center gap-2">
          <span
            className={
              reached(it.id)
                ? "flex h-7 w-7 items-center justify-center rounded-full bg-accent-600 text-ink-50"
                : "flex h-7 w-7 items-center justify-center rounded-full border border-ink-700 text-ink-400"
            }
          >
            {it.n}
          </span>
          <span className={reached(it.id) ? "text-ink-100" : "text-ink-500"}>
            {it.label}
          </span>
          {i < items.length - 1 ? (
            <span className="ml-2 h-px w-8 bg-ink-700" />
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function IntroStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-medium text-ink-50">
          Colleghiamo il tuo account Google DV360
        </h1>
        <p className="mt-3 text-sm text-ink-300">
          Per ottimizzare il bidding su DV360, DeevAI deve leggere le
          metriche dal Bid Manager Reporting e aggiornare i bid modifiers
          sui line item via API. Servono due cose.
        </p>
      </div>

      <ul className="space-y-4 text-sm text-ink-200">
        <Requirement
          n="1"
          title="Un OAuth Client su Google Cloud Console"
          body="Console Google Cloud → APIs &amp; Services → Credentials → Create Credentials → OAuth client ID, tipo &laquo;Web application&raquo;. Aggiungi http://localhost:3000/onboarding/dv360 come Authorized redirect URI (in produzione metterai il tuo dominio). Annota Client ID e Client Secret."
        />
        <Requirement
          n="2"
          title="API abilitate sul progetto"
          body="Sempre in Google Cloud, abilita due API: &laquo;Display &amp; Video 360 API&raquo; e &laquo;DoubleClick Bid Manager API&raquo;. L'utente Google che fa il consenso deve essere mappato come utente DV360 con i permessi giusti."
        />
      </ul>

      <div className="rounded-md border border-amber-900/60 bg-amber-900/20 px-4 py-3 text-xs text-amber-200">
        I primi 14 giorni DeevAI gira in <strong>observation only</strong> —
        proponiamo decisioni ma non tocchiamo i tuoi bid modifier. È una
        garanzia di prodotto, non una limitazione.
      </div>

      <button
        onClick={onNext}
        className="w-full rounded-md bg-accent-600 px-4 py-2.5 text-sm font-medium text-ink-50 hover:bg-accent-700"
      >
        Ho tutto pronto → Connetti
      </button>
    </div>
  );
}

function Requirement({
  n,
  title,
  body,
}: {
  n: string;
  title: string;
  body: string;
}) {
  return (
    <li className="flex gap-3 rounded-lg border border-ink-800 bg-ink-800/40 p-4">
      <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-ink-700 text-xs font-medium text-ink-100">
        {n}
      </span>
      <div>
        <div className="font-medium text-ink-50">{title}</div>
        <div
          className="mt-1 text-xs leading-relaxed text-ink-300"
          dangerouslySetInnerHTML={{ __html: body }}
        />
      </div>
    </li>
  );
}

function ConnectStep({
  form,
  setForm,
  onSubmit,
  onBack,
  loading,
  error,
}: {
  form: FormState;
  setForm: (f: FormState) => void;
  onSubmit: (e: React.FormEvent) => void;
  onBack: () => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <h1 className="text-2xl font-medium text-ink-50">Connetti DV360</h1>
      <p className="text-sm text-ink-300">
        Incolla le credenziali del tuo OAuth client. Il client_secret viene
        cifrato at-rest — non lo vediamo mai in chiaro.
      </p>

      <Field label="Nome della connessione" hint="Solo per la dashboard">
        <input
          type="text"
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className={inputCls}
        />
      </Field>

      <Field label="OAuth Client ID">
        <input
          type="text"
          required
          minLength={10}
          value={form.client_id}
          onChange={(e) => setForm({ ...form, client_id: e.target.value })}
          className={`${inputCls} font-mono text-xs`}
          placeholder="xxxxxxxxxxxx.apps.googleusercontent.com"
        />
      </Field>

      <Field label="OAuth Client Secret">
        <input
          type="password"
          required
          minLength={10}
          value={form.client_secret}
          onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
          className={`${inputCls} font-mono text-xs`}
          placeholder="••••••••••••••••••••••••"
        />
      </Field>

      {error ? (
        <div className="rounded-md border border-red-900 bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-md border border-ink-700 px-4 py-2.5 text-sm text-ink-200 hover:border-ink-500"
        >
          ← Indietro
        </button>
        <button
          type="submit"
          disabled={loading}
          className="flex-1 rounded-md bg-accent-600 px-4 py-2.5 text-sm font-medium text-ink-50 hover:bg-accent-700 disabled:opacity-60"
        >
          {loading ? "Connetto..." : "Connetti e vai al consenso Google →"}
        </button>
      </div>
    </form>
  );
}

function ExchangingStep() {
  return (
    <div className="space-y-3 text-center">
      <h1 className="text-xl font-medium text-ink-50">
        Sto completando l'autenticazione…
      </h1>
      <p className="text-sm text-ink-300">
        Scambio il codice di autorizzazione con Google e leggo la lista
        advertiser. Un attimo.
      </p>
      <div className="mx-auto mt-6 h-6 w-6 animate-spin rounded-full border-2 border-accent-600 border-t-transparent" />
    </div>
  );
}

function AdvertiserStep({
  advertisers,
  chosen,
  onPick,
  onConfirm,
  loading,
  error,
}: {
  advertisers: Dv360AdvertiserRead[];
  chosen: string | null;
  onPick: (id: string) => void;
  onConfirm: () => void;
  loading: boolean;
  error: string | null;
}) {
  if (advertisers.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-medium text-ink-50">
          Nessun advertiser trovato
        </h1>
        <p className="text-sm text-ink-300">
          Il consenso è andato a buon fine ma l'utente Google che hai usato
          non vede nessun advertiser DV360. Verifica i permessi e riprova.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-medium text-ink-50">
          Scegli un advertiser
        </h1>
        <p className="mt-2 text-sm text-ink-300">
          DeevAI gestirà i line item di questo advertiser. Puoi collegarne
          altri in seguito.
        </p>
      </div>

      <ul className="space-y-2">
        {advertisers.map((a) => {
          const isPicked = a.advertiser_id === chosen;
          return (
            <li key={a.advertiser_id}>
              <button
                type="button"
                onClick={() => onPick(a.advertiser_id)}
                className={
                  "flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left text-sm transition " +
                  (isPicked
                    ? "border-accent-500 bg-accent-600/10 text-ink-50"
                    : "border-ink-800 bg-ink-800/40 text-ink-200 hover:border-ink-600")
                }
              >
                <div>
                  <div className="font-medium">{a.display_name}</div>
                  <div className="mt-0.5 text-[11px] text-ink-400">
                    ID {a.advertiser_id}
                    {a.partner_id ? ` · Partner ${a.partner_id}` : ""}
                    {a.currency_code ? ` · ${a.currency_code}` : ""}
                    {a.timezone ? ` · ${a.timezone}` : ""}
                  </div>
                </div>
                {a.entity_status ? (
                  <span className="text-[10px] uppercase tracking-wide text-ink-500">
                    {a.entity_status.replace("ENTITY_STATUS_", "")}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      {error ? (
        <div className="rounded-md border border-red-900 bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      <button
        onClick={onConfirm}
        disabled={!chosen || loading}
        className="w-full rounded-md bg-accent-600 px-4 py-2.5 text-sm font-medium text-ink-50 hover:bg-accent-700 disabled:opacity-60"
      >
        {loading ? "Salvo..." : "Conferma e vai alla dashboard →"}
      </button>
    </div>
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
      <span className="mb-1 block text-xs font-medium text-ink-200">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11px] text-ink-500">{hint}</span>
      ) : null}
    </label>
  );
}
