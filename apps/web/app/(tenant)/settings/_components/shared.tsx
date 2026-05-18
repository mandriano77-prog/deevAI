export const selectCls =
  "mt-1 w-full max-w-xs rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50 focus:border-amber-500/60 focus:outline-none focus:ring-1 focus:ring-amber-500/40";

export const inputCls =
  "mt-1 w-full rounded-md border border-ink-700 bg-ink-800 px-3 py-2 text-sm text-ink-50 focus:border-amber-500/60 focus:outline-none";

export const sectionCls = "rounded-lg border border-ink-800 bg-ink-900/80 px-5";
export const microcopy = "Le modifiche si applicano al prossimo run.";

export function weightValueWarning(weight: number, valueEur: number): string | null {
  const max = Math.max(weight, valueEur, 0.01);
  const ratio = Math.abs(weight - valueEur) / max;
  if (ratio > 10) {
    return "Peso e valore € molto disallineati — verifica che sia intenzionale.";
  }
  return null;
}

export function SettingRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  const labelId = `setting-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="flex flex-col gap-3 border-b border-ink-800 py-4 last:border-0 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div id={labelId} className="text-sm font-medium text-ink-100">
          {label}
        </div>
        {hint ? <p className="mt-0.5 text-xs text-ink-400">{hint}</p> : null}
      </div>
      <div className="shrink-0" aria-labelledby={labelId}>
        {children}
      </div>
    </div>
  );
}
