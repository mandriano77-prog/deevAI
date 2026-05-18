"use client";

import { useState } from "react";

import type { ActionRead } from "@/lib/api/actions";
import { microcopy, sectionCls, weightValueWarning } from "./shared";
import { ActionFormModal } from "./ActionFormModal";

interface Props {
  actions: ActionRead[];
  onCreate: (data: {
    name: string;
    type: string;
    weight: number;
    value_eur: number;
  }) => Promise<void>;
  onUpdate: (
    id: string,
    data: { name: string; type: string; weight: number; value_eur: number },
  ) => Promise<void>;
  onArchive: (id: string) => Promise<void>;
}

export function ActionCatalog({
  actions,
  onCreate,
  onUpdate,
  onArchive,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ActionRead | null>(null);

  return (
    <section aria-labelledby="actions-heading">
      <div className="mb-2 flex items-center justify-between">
        <h2 id="actions-heading" className="text-sm font-medium text-ink-50">
          Catalogo action
        </h2>
        <button
          type="button"
          className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-ink-950 hover:bg-amber-500"
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
        >
          Aggiungi action
        </button>
      </div>
      <div className={sectionCls}>
        <ul className="divide-y divide-ink-800">
          {actions.map((a) => {
            const warn = weightValueWarning(Number(a.weight), Number(a.value_eur));
            return (
              <li
                key={a.id}
                className="flex flex-wrap items-center justify-between gap-2 py-3"
              >
                <div>
                  <span className="font-medium text-ink-100">{a.name}</span>
                  <span className="ml-2 text-xs text-ink-500">{a.type}</span>
                  <p className="text-xs text-ink-400">
                    peso {a.weight} · {a.value_eur} €
                  </p>
                  {warn ? (
                    <p className="text-xs text-amber-300">⚠ {warn}</p>
                  ) : null}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-xs text-ink-300 hover:text-ink-50"
                    onClick={() => {
                      setEditing(a);
                      setModalOpen(true);
                    }}
                  >
                    Modifica
                  </button>
                  <button
                    type="button"
                    className="text-xs text-red-300 hover:text-red-200"
                    onClick={() => void onArchive(a.id)}
                  >
                    Archivia
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
        {actions.length === 0 ? (
          <p className="py-4 text-sm text-ink-500">Nessuna action definita.</p>
        ) : null}
      </div>
      <p className="mt-2 text-xs text-ink-500">{microcopy}</p>
      <ActionFormModal
        open={modalOpen}
        initial={editing}
        onClose={() => setModalOpen(false)}
        onSave={async (data) => {
          if (editing) await onUpdate(editing.id, data);
          else await onCreate(data);
        }}
      />
    </section>
  );
}
