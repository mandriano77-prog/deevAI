"use client";

import { useState } from "react";

import { inputCls, microcopy, selectCls } from "./shared";

export interface HardConstraintFormBody {
  metric: string;
  operator: string;
  value: number;
  violation_policy: string;
}

interface Props {
  onSubmit: (body: HardConstraintFormBody) => Promise<void>;
}

export function HardConstraintForm({ onSubmit }: Props) {
  const [metric, setMetric] = useState("cpc");
  const [operator, setOperator] = useState("lte");
  const [value, setValue] = useState("0.15");
  const [policy, setPolicy] = useState("freeze");

  return (
    <form
      className="mt-4 grid gap-2 border-t border-ink-800 pt-4 sm:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault();
        void onSubmit({
          metric,
          operator,
          value: Number(value),
          violation_policy: policy,
        });
      }}
    >
      <select
        className={selectCls}
        value={metric}
        onChange={(e) => {
          setMetric(e.target.value);
          if (["cpc", "cpm", "cpcv", "fraud_rate"].includes(e.target.value)) {
            setOperator("lte");
          } else {
            setOperator("gte");
          }
        }}
        aria-label="Metrica constraint"
      >
        <option value="cpc">cpc</option>
        <option value="viewability">viewability</option>
        <option value="fraud_rate">fraud_rate</option>
        <option value="roas">roas</option>
      </select>
      <select
        className={selectCls}
        value={operator}
        onChange={(e) => setOperator(e.target.value)}
        aria-label="Operatore constraint"
      >
        <option value="lte">≤</option>
        <option value="gte">≥</option>
      </select>
      <input
        className={inputCls}
        type="number"
        step="0.001"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Valore soglia constraint"
      />
      <select
        className={selectCls}
        value={policy}
        onChange={(e) => setPolicy(e.target.value)}
        aria-label="Policy violazione constraint"
      >
        <option value="freeze">freeze</option>
        <option value="throttle">throttle</option>
        <option value="kill">kill</option>
        <option value="alert">alert</option>
      </select>
      <button
        type="submit"
        className="sm:col-span-4 rounded-md bg-ink-700 px-3 py-2 text-sm text-ink-100 hover:bg-ink-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-500"
      >
        Aggiungi constraint
      </button>
      <p className="sm:col-span-4 text-xs text-ink-500">{microcopy}</p>
    </form>
  );
}
