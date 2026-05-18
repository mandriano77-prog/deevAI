const steps = [
  {
    title: "Colleghi la DSP",
    body: "Google OAuth (DV360), profilo advertiser e line item. I token restano cifrati, mai in chiaro nei log.",
  },
  {
    title: "Osservi 14 giorni",
    body: "DeevAI legge AMC, calcola il CPV per dimensione e propone aggiustamenti. Nessuna modifica live senza il tuo via libera.",
  },
  {
    title: "Ricevi il brief del lunedì",
    body: "Un riepilogo in italiano, le decisioni da approvare, poi applicazione su DSP quando sei pronto.",
  },
];

export function HowItWorks() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <h2 className="text-center text-xs uppercase tracking-wider text-ink-400">
        Come funziona
      </h2>
      <p className="mt-2 text-center text-2xl font-medium text-ink-50">
        Tre passi, un ciclo settimanale
      </p>
      <ol className="mt-12 grid gap-6 md:grid-cols-3">
        {steps.map((step, i) => (
          <li
            key={step.title}
            className="rounded-lg border border-ink-800 bg-ink-900/80 p-6"
          >
            <span className="font-mono text-sm text-accent-400">0{i + 1}</span>
            <h3 className="mt-3 text-lg font-medium text-ink-50">{step.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-300">
              {step.body}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
