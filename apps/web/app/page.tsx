import Link from "next/link";

import { Audience } from "@/components/landing/audience";
import { DemoPreview } from "@/components/landing/demo-preview";
import { HowItWorks } from "@/components/landing/how-it-works";
import { Wordmark } from "@/components/wordmark";

export default function HomePage() {
  return (
    <main className="relative isolate overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 [background-image:linear-gradient(to_right,#1a1a18_1px,transparent_1px),linear-gradient(to_bottom,#1a1a18_1px,transparent_1px)] [background-size:64px_64px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]"
      />

      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 pt-8">
        <Wordmark variant="logo" className="text-xl" />
        <nav className="flex items-center gap-6 text-sm text-ink-200">
          <a href="#demo" className="hover:text-ink-50">
            Demo
          </a>
          <a href="#come-funziona" className="hover:text-ink-50">
            Come funziona
          </a>
          <Link href="/login" className="hover:text-ink-50">
            Accedi
          </Link>
          <Link
            href="/signup"
            className="rounded-md border border-ink-600 px-3 py-1.5 text-ink-50 transition hover:border-accent-400 hover:text-accent-400"
          >
            Richiedi accesso
          </Link>
        </nav>
      </header>

      <section className="mx-auto flex max-w-4xl flex-col items-center px-6 pt-24 pb-16 text-center">
        <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-ink-600 px-3 py-1 text-xs uppercase tracking-wider text-ink-200">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent-400" />
          Beta privata · advertiser Google DV360
        </p>

        <h1 className="font-sans text-5xl font-medium tracking-tight sm:text-6xl md:text-7xl">
          <Wordmark variant="logo" />
        </h1>

        <p className="mt-10 max-w-2xl text-lg leading-relaxed text-ink-100 sm:text-xl">
          Ogni lunedì mattina, le tue campagne Google DV360 ricevono un brief di una
          pagina: cosa è successo, cosa cambieremmo, quanto costa. Tu approvi.
          DeevAI applica.
        </p>

        <div className="mt-12 flex flex-col items-center gap-3 sm:flex-row">
          <Link
            href="/signup"
            className="rounded-md bg-accent-600 px-5 py-2.5 text-sm font-medium text-ink-50 transition hover:bg-accent-700"
          >
            Richiedi accesso
          </Link>
          <a
            href="#demo"
            className="text-sm text-ink-200 underline-offset-4 hover:text-ink-50 hover:underline"
          >
            Vedi l&apos;anteprima demo →
          </a>
        </div>

        <p className="mt-6 text-xs text-ink-400">
          14 giorni solo osservazione prima di qualsiasi modifica. Resti in controllo.
        </p>
      </section>

      <div id="demo">
        <DemoPreview />
      </div>

      <div id="come-funziona">
        <HowItWorks />
      </div>

      <Audience />

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h2 className="text-2xl font-medium text-ink-50">
          Pronto a collegare il tuo seat?
        </h2>
        <p className="mt-3 text-sm text-ink-300">
          Setup in pochi minuti. Primo run settimanale dopo la connessione DSP.
        </p>
        <Link
          href="/signup"
          className="mt-8 inline-block rounded-md bg-accent-600 px-6 py-3 text-sm font-medium text-ink-50 hover:bg-accent-700"
        >
          Inizia con DeevAI
        </Link>
      </section>

      <footer className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 border-t border-ink-800 px-6 py-8 text-xs text-ink-400 sm:flex-row">
        <Wordmark variant="logo" className="text-sm" />
        <div className="flex gap-4">
          <Link href="/privacy" className="hover:text-ink-200">
            Privacy
          </Link>
          <Link href="/terms" className="hover:text-ink-200">
            Termini
          </Link>
        </div>
        <span>© 2026 · Per advertiser Google DV360, non da Google.</span>
      </footer>
    </main>
  );
}
