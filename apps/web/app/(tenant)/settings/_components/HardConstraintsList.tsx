"use client";

import type { HardConstraintRead } from "@/lib/api/optimization";
import { microcopy, sectionCls } from "./shared";
import { HardConstraintForm, type HardConstraintFormBody } from "./HardConstraintForm";

interface Props {
  strategyId: string | null;
  constraints: HardConstraintRead[];
  onCreate: (body: HardConstraintFormBody) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

export function HardConstraintsList({
  strategyId,
  constraints,
  onCreate,
  onDelete,
}: Props) {
  if (!strategyId) {
    return (
      <section>
        <h2 className="mb-2 text-sm font-medium text-ink-50">Hard constraint</h2>
        <p className="text-sm text-ink-500">
          Salva prima una strategia di ottimizzazione per aggiungere constraint.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="constraints-heading">
      <h2 id="constraints-heading" className="mb-2 text-sm font-medium text-ink-50">
        Hard constraint
      </h2>
      <div className={sectionCls}>
        <ul className="divide-y divide-ink-800" role="list">
          {constraints.map((c) => (
            <li
              key={c.id}
              className="flex items-center justify-between py-3 text-sm text-ink-200"
            >
              <span>
                {c.metric} {c.operator} {c.value} → {c.violation_policy}
              </span>
              <button
                type="button"
                className="text-xs text-red-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-500"
                onClick={() => void onDelete(c.id)}
              >
                Rimuovi
              </button>
            </li>
          ))}
        </ul>
        <HardConstraintForm onSubmit={onCreate} />
      </div>
      <p className="mt-2 text-xs text-ink-500">{microcopy}</p>
    </section>
  );
}
