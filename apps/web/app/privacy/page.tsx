import Link from "next/link";

import { Wordmark } from "@/components/wordmark";

export const metadata = {
  title: "Privacy",
  description: "Privacy notice for DeevAI.",
};

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-12 flex items-center justify-between">
        <Link href="/" className="text-sm text-ink-400 hover:text-ink-200">
          ← Home
        </Link>
        <Wordmark variant="text" className="text-sm" />
      </header>

      <article className="space-y-6 text-sm leading-relaxed text-ink-200">
        <h1 className="text-3xl font-medium text-ink-50">Privacy notice</h1>
        <p className="text-xs text-ink-400">Ultimo aggiornamento: maggio 2026</p>

        <section className="space-y-4">
          <p>
            <strong className="font-medium text-ink-50">Chi siamo.</strong>{" "}
            DeevAI è un prodotto SaaS sviluppato per advertiser e agenzie che
            usano Google DV360. Questa notice descrive come trattiamo i tuoi dati
            personali e i dati di campagna che colleghi a DeevAI.
          </p>

          <p>
            <strong className="font-medium text-ink-50">Dati raccolti.</strong>{" "}
            Quando crei un account raccogliamo: email, nome (opzionale),
            password (hashata via bcrypt, mai in chiaro), nome del workspace.
            Non raccogliamo dati di pagamento direttamente — durante la beta
            la fatturazione è manuale.
          </p>

          <p>
            <strong className="font-medium text-ink-50">
              Dati Google DV360.
            </strong>{" "}
            Quando colleghi il tuo seat Google DV360 via OAuth, riceviamo un
            refresh token che ci permette di leggere i tuoi dati di
            performance via DV360 Reporting e applicare bid
            adjustments via Google DV360 API. Il refresh token è cifrato
            at-rest tramite AWS KMS — nessun essere umano in DeevAI vede mai
            quel token in chiaro. Non condividiamo i tuoi dati di campagna
            con terze parti.
          </p>

          <p>
            <strong className="font-medium text-ink-50">
              Dove sono i dati.
            </strong>{" "}
            Tutti i dati sono ospitati nella region EU (Frankfurt) su AWS.
            Nessun dato lascia l'Unione Europea.
          </p>

          <p>
            <strong className="font-medium text-ink-50">I tuoi diritti.</strong>{" "}
            Hai diritto di accesso, rettifica, cancellazione, portabilità e
            opposizione al trattamento dei tuoi dati (GDPR Art. 15–22). Per
            esercitarli scrivi a{" "}
            <a
              href="mailto:privacy@deevai.app"
              className="text-accent-400 hover:text-accent-300"
            >
              privacy@deevai.app
            </a>
            . Cancelliamo i tuoi dati entro 30 giorni dalla richiesta.
          </p>

          <p>
            <strong className="font-medium text-ink-50">Cookie.</strong>{" "}
            DeevAI non usa cookie di tracking né analytics di terze parti.
            L'unico cookie che salviamo è il tuo token di sessione (JWT) in
            localStorage, necessario per mantenere il login.
          </p>

          <p>
            <strong className="font-medium text-ink-50">Contatto DPO.</strong>{" "}
            Per qualsiasi richiesta su trattamento dei dati o data processing
            agreement (DPA), contattaci a{" "}
            <a
              href="mailto:privacy@deevai.app"
              className="text-accent-400 hover:text-accent-300"
            >
              privacy@deevai.app
            </a>
            .
          </p>
        </section>

        <p className="text-xs text-ink-500">
          Questa privacy notice è un draft della private beta. La versione
          legale definitiva sarà pubblicata prima del general availability.
        </p>
      </article>
    </main>
  );
}
