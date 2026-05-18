"use client";

import type { SettingRead, SettingUpdate } from "@/lib/api";
import { microcopy, sectionCls, selectCls, SettingRow } from "./shared";

const CTR_OPTIONS = [
  { value: "0.02", label: "2,00%" },
  { value: "0.03", label: "3,00%" },
  { value: "0.04", label: "4,00%" },
  { value: "0.05", label: "5,00%" },
];
const VIEWABILITY_OPTIONS = [
  { value: "0.30", label: "30%" },
  { value: "0.40", label: "40%" },
  { value: "0.50", label: "50%" },
];
const IMPRESSIONS_OPTIONS = [
  { value: "500", label: "500" },
  { value: "1000", label: "1.000" },
];
const VISITS_OPTIONS = [
  { value: "10", label: "10" },
  { value: "20", label: "20" },
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

export function SafetyFilters({ data, saving, onPatch }: Props) {
  return (
    <section aria-labelledby="safety-heading">
      <h2 id="safety-heading" className="mb-2 text-sm font-medium text-ink-50">
        Filtri di sicurezza
      </h2>
      <div className={sectionCls}>
        <SettingRow label="Soglia CTR anomala (anti-bot)">
          <select
            className={selectCls}
            disabled={saving}
            value={nearest(data.anomalous_ctr_threshold, CTR_OPTIONS)}
            onChange={(e) =>
              void onPatch({ anomalous_ctr_threshold: Number(e.target.value) })
            }
          >
            {CTR_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Viewability minima">
          <select
            className={selectCls}
            disabled={saving}
            value={nearest(data.min_viewability, VIEWABILITY_OPTIONS)}
            onChange={(e) => void onPatch({ min_viewability: Number(e.target.value) })}
          >
            {VIEWABILITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Impression minime per agire">
          <select
            className={selectCls}
            disabled={saving}
            value={String(data.min_impressions_for_action)}
            onChange={(e) =>
              void onPatch({ min_impressions_for_action: Number(e.target.value) })
            }
          >
            {IMPRESSIONS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Visite minime per azione forte">
          <select
            className={selectCls}
            disabled={saving}
            value={String(data.min_visits_for_strong_action)}
            onChange={(e) =>
              void onPatch({ min_visits_for_strong_action: Number(e.target.value) })
            }
          >
            {VISITS_OPTIONS.map((o) => (
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
