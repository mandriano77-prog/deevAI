"use client";

import { useState } from "react";

import type { ActionRead } from "@/lib/api/actions";
import { inputCls, weightValueWarning } from "./shared";

interface Props {
  open: boolean;
  initial?: ActionRead | null;
  onClose: () => void;
  onSave: (data: {
    name: string;
    type: string;
    weight: number;
    value_eur: number;
  }) => Promise<void>;
}

export function ActionFormModal({ open, initial, onClose, onSave }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [type, setType] = useState(initial?.type ?? "visit");
  const [weight, setWeight] = useState(String(initial?.weight ?? 1));
  const [valueEur, setValueEur] = useState(String(initial?.value_eur ?? 0));
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  const w = Number(weight);
  const v = Number(valueEur);
  const warn = weightValueWarning(w, v);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="action-form-title"
    >
      <form
        className="w-full max-w-md rounded-lg border border-ink-700 bg-ink-900 p-6 shadow-xl"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await onSave({ name, type, weight: w, value_eur: v });
            onClose();
          } finally {
            setBusy(false);
          }
        }}
      >
        <h3 id="action-form-title" className="text-lg font-medium text-ink-50">
          {initial ? "Modifica action" : "Nuova action"}
        </h3>
        <label className="mt-4 block text-xs text-ink-400">
          Nome
          <input
            className={inputCls}
            value={name}
            required
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="mt-3 block text-xs text-ink-400">
          Tipo
          <select
            className={inputCls}
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="visit">visit</option>
            <option value="lead">lead</option>
            <option value="purchase">purchase</option>
            <option value="engagement">engagement</option>
            <option value="custom">custom</option>
          </select>
        </label>
        <label className="mt-3 block text-xs text-ink-400">
          Peso
          <input
            type="number"
            step="0.01"
            className={inputCls}
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
        </label>
        <label className="mt-3 block text-xs text-ink-400">
          Valore €
          <input
            type="number"
            step="0.01"
            className={inputCls}
            value={valueEur}
            onChange={(e) => setValueEur(e.target.value)}
          />
        </label>
        {warn ? (
          <p className="mt-2 text-xs text-amber-300" role="status">
            ⚠ {warn}
          </p>
        ) : null}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md px-3 py-2 text-sm text-ink-300 hover:bg-ink-800"
            onClick={onClose}
          >
            Annulla
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-amber-600 px-3 py-2 text-sm font-medium text-ink-950 hover:bg-amber-500 disabled:opacity-50"
          >
            Salva
          </button>
        </div>
      </form>
    </div>
  );
}
