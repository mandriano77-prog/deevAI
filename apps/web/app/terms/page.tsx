import Link from "next/link";

import { Wordmark } from "@/components/wordmark";

export const metadata = {
  title: "Termini di servizio",
};

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-12 flex items-center justify-between">
        <Link href="/" className="text-sm text-ink-400 hover:text-ink-200">
          ← Home
        </Link>
        <Wordmark variant="text" className="text-sm" />
      </header>

      <article className="space-y-6 text-sm leading-relaxed text-ink-200">
        <h1 className="text-3xl font-medium text-ink-50">Termini di servizio</h1>
        <p className="text-xs text-ink-400">Ultimo aggiornamento: maggio 2026</p>

        <p>
          deevAI è in private beta. I termini contrattuali definitivi saranno
          pubblicati al general availability. Durante la beta usi deevAI a
          tue spese e rischio, e accetti che alcune feature possano cambiare
          o essere temporaneamente non disponibili.
        </p>

        <p>
          <strong className="font-medium text-ink-50">Limitazione di responsabilità.</strong>{" "}
          deevAI propone decisioni di ottimizzazione del bidding ma non
          garantisce risultati specifici. Sei sempre tu a controllare quali
          decisioni vengono applicate al tuo account Google DV360. deevAI non è
          responsabile per perdite economiche derivanti da decisioni applicate.
        </p>

        <p>
          <strong className="font-medium text-ink-50">Cancellazione.</strong>{" "}
          Puoi cancellare il tuo account in qualsiasi momento dalle settings.
          Tutti i tuoi dati vengono eliminati entro 30 giorni dalla richiesta.
        </p>

        <p>
          <strong className="font-medium text-ink-50">Modifiche.</strong>{" "}
          Possiamo aggiornare questi termini con preavviso di 30 giorni via
          email all'indirizzo registrato.
        </p>

        <p>
          Per qualunque domanda:{" "}
          <a
            href="mailto:hello@deevai.app"
            className="text-accent-400 hover:text-accent-300"
          >
            hello@deevai.app
          </a>
          .
        </p>
      </article>
    </main>
  );
}
