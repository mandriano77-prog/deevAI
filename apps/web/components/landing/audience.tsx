const audiences = [
  {
    title: "Agenzie media",
    body: "Gestisci più seat DSP con un brief settimanale per brand, senza export manuali da AMC.",
  },
  {
    title: "Brand in-house",
    body: "Un solo workspace, CPV target per line item, controllo totale prima di ogni apply.",
  },
  {
    title: "Freelance programmatic",
    body: "Automazione del tuning con guardrail: step massimo, click-farm filter, 14 giorni osservazione.",
  },
];

export function Audience() {
  return (
    <section className="mx-auto max-w-6xl border-t border-ink-800 px-6 py-20">
      <h2 className="text-center text-xs uppercase tracking-wider text-ink-400">
        Per chi è
      </h2>
      <p className="mt-2 text-center text-2xl font-medium text-ink-50">
        Chi gestisce Google DV360 in Italia
      </p>
      <ul className="mt-12 grid gap-6 md:grid-cols-3">
        {audiences.map((item) => (
          <li
            key={item.title}
            className="rounded-lg border border-dashed border-ink-700 p-6"
          >
            <h3 className="font-medium text-ink-50">{item.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-300">
              {item.body}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
