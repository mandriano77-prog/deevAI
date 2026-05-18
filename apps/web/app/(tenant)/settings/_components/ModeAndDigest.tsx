"use client";

import type { SettingRead, SettingUpdate } from "@/lib/api";
import { microcopy, sectionCls, selectCls, SettingRow } from "./shared";

const LANGUAGE_OPTIONS = [
  { value: "it", label: "Italiano" },
  { value: "en", label: "English" },
];
const POST_OBSERVATION_MODE_OPTIONS = [
  { value: "approval_required", label: "Richiede approvazione" },
  { value: "auto_apply", label: "Applica automaticamente" },
];
const EMAIL_DIGEST_OPTIONS = [
  { value: "true", label: "Sì, invia email" },
  { value: "false", label: "No, solo in dashboard" },
];

function formatObservationUntil(iso: string | null): string {
  if (!iso) return "Non impostata";
  return new Date(iso).toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

interface Props {
  data: SettingRead;
  saving: boolean;
  onPatch: (p: SettingUpdate) => Promise<void>;
}

export function ModeAndDigest({ data, saving, onPatch }: Props) {
  const observationActive =
    data.observation_only_until != null &&
    new Date(data.observation_only_until).getTime() > Date.now();

  return (
    <section aria-labelledby="mode-heading">
      <h2 id="mode-heading" className="mb-2 text-sm font-medium text-ink-50">
        Modalità e digest
      </h2>
      <div className={sectionCls}>
        <SettingRow
          label="Stato attuale"
          hint={
            observationActive
              ? `Observation only fino al ${formatObservationUntil(data.observation_only_until)}`
              : "Finestra di osservazione conclusa"
          }
        >
          <span className="mt-1 inline-block rounded-md border border-amber-800/60 bg-amber-900/30 px-3 py-2 text-sm text-amber-100">
            {observationActive ? "Observation only" : "Attivo"}
          </span>
        </SettingRow>
        <SettingRow label="Dopo l'osservazione">
          <select
            className={selectCls}
            disabled={saving}
            value={data.default_line_item_mode}
            onChange={(e) =>
              void onPatch({
                default_line_item_mode:
                  e.target.value as SettingUpdate["default_line_item_mode"],
              })
            }
          >
            {POST_OBSERVATION_MODE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Lingua del digest">
          <select
            className={selectCls}
            disabled={saving}
            value={data.digest_language}
            onChange={(e) =>
              void onPatch({
                digest_language: e.target.value as SettingUpdate["digest_language"],
              })
            }
          >
            {LANGUAGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </SettingRow>
        <SettingRow label="Digest via email">
          <select
            className={selectCls}
            disabled={saving}
            value={String(data.digest_delivery_email)}
            onChange={(e) => void onPatch({ digest_delivery_email: e.target.value === "true" })}
          >
            {EMAIL_DIGEST_OPTIONS.map((o) => (
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
