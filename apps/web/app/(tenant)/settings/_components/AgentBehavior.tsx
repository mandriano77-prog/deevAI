"use client";

import type { SettingRead, SettingUpdate } from "@/lib/api";
import { microcopy, sectionCls, selectCls, SettingRow } from "./shared";

const CPV_OPTIONS = [
  { value: "0.40", label: "0,40 €" },
  { value: "0.50", label: "0,50 €" },
  { value: "0.60", label: "0,60 €" },
];
const TOLERANCE_OPTIONS = [
  { value: "0.15", label: "±15%" },
  { value: "0.20", label: "±20%" },
  { value: "0.25", label: "±25%" },
];
const MAX_STEP_OPTIONS = [
  { value: "0.20", label: "0,20" },
  { value: "0.25", label: "0,25" },
  { value: "0.30", label: "0,30" },
];
const MAX_MODIFIER_OPTIONS = [
  { value: "2.00", label: "2,00×" },
  { value: "2.50", label: "2,50×" },
];

function nearest(value: number, options: { value: string }[]) {
  const s = String(value);
  return options.some((o) => o.value === s)
    ? s
    : options.reduce((a, b) =>
        Math.abs(Number(a.value) - value) < Math.abs(Number(b.value) - value) ? a : b,
      ).value;
}

interface Props {
  data: SettingRead;
  saving: boolean;
  onPatch: (p: SettingUpdate) => Promise<void>;
}

export function AgentBehavior({ data, saving, onPatch }: Props) {
  return (
    <section aria-labelledby="agent-heading">
      <h2 id="agent-heading" className="mb-2 text-sm font-medium text-ink-50">
        Comportamento agente
      </h2>
      <div className={sectionCls}>
        <SettingRow label="CPV target default">
          <select
            className={selectCls}
            disabled={saving}
            value={nearest(data.default_cpv_target, CPV_OPTIONS)}
            onChange={(e) => void onPatch({ default_cpv_target: Number(e.target.value) })}
          >
            {CPV_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Banda tolleranza">
          <select
            className={selectCls}
            disabled={saving}
            value={nearest(data.tolerance_band, TOLERANCE_OPTIONS)}
            onChange={(e) => void onPatch({ tolerance_band: Number(e.target.value) })}
          >
            {TOLERANCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Passo massimo per run">
          <select
            className={selectCls}
            disabled={saving}
            value={nearest(data.max_step_per_run, MAX_STEP_OPTIONS)}
            onChange={(e) => void onPatch({ max_step_per_run: Number(e.target.value) })}
          >
            {MAX_STEP_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Modifier massimo">
          <select
            className={selectCls}
            disabled={saving}
            value={nearest(data.max_modifier, MAX_MODIFIER_OPTIONS)}
            onChange={(e) => void onPatch({ max_modifier: Number(e.target.value) })}
          >
            {MAX_MODIFIER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
      </div>
      <p className="mt-2 text-xs text-ink-500">{microcopy}</p>
    </section>
  );
}
