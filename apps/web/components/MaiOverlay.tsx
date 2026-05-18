"use client";

import { useState } from "react";

import { useMaiLineItemId } from "@/lib/hooks/useMaiLineItem";
import { ApiError } from "@/lib/api";
import { maiApi, type MaiAskResponse } from "@/lib/api/mai";

interface Props {
  onClose: () => void;
}

function formatApiError(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: unknown } | undefined;
    const inner =
      d && typeof d === "object" && "detail" in d ? (d as { detail?: unknown }).detail : undefined;
    if (typeof inner === "string") return inner;
    if (inner !== undefined) return JSON.stringify(inner);
    return e.message;
  }
  return "Operazione non riuscita";
}

export function MaiOverlay({ onClose }: Props) {
  const { lineItemId, loading: liLoading, error: liError } = useMaiLineItemId();
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<MaiAskResponse | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    if (!lineItemId) {
      setError(liError ?? "Line item non disponibile.");
      return;
    }
    setLoading(true);
    setDraft(null);
    setFeedback(null);
    setError(null);
    try {
      const data = await maiApi.ask(prompt.trim(), lineItemId);
      setDraft(data);
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }

  async function confirm() {
    if (!draft || draft.type === "query" || draft.type === "system") return;
    if (!draft.payload) return;
    const intent = draft.intent;
    setLoading(true);
    setFeedback(null);
    setError(null);
    try {
      const res = await maiApi.execute(intent, draft.payload);
      setFeedback(res.message);
      setDraft(null);
      setPrompt("");
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("mai-executed", { detail: { intent } }));
      }
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }

  const isDirectAnswer = draft?.type === "query" || draft?.type === "system";
  const busy = loading || liLoading;

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-50 flex max-h-[85vh] flex-col overflow-hidden rounded-t-2xl border border-amber-500/20 bg-neutral-950 shadow-2xl sm:inset-x-auto sm:bottom-24 sm:right-6 sm:left-auto sm:max-h-[80vh] sm:w-[min(100vw-2rem,420px)] sm:rounded-2xl"
      role="dialog"
      aria-labelledby="mai-overlay-title"
    >
      <div className="flex items-center justify-between border-b border-white/5 p-4">
        <span id="mai-overlay-title" className="font-bold text-amber-500">
          M.AI
        </span>
        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-neutral-500 sm:inline">Claude Sonnet 4.6</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-xs text-neutral-400 hover:bg-white/10"
            aria-label="Chiudi overlay M.AI"
          >
            Chiudi
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {liError ? (
          <p className="mb-2 text-xs text-amber-400" role="status">
            {liError}
          </p>
        ) : null}
        <textarea
          rows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Cosa vogliamo guardare oggi?"
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-500"
          aria-label="Prompt M.AI"
          disabled={busy}
        />
        <button
          type="button"
          onClick={() => void ask()}
          disabled={busy || !prompt.trim() || !lineItemId}
          className="mt-2 w-full rounded-lg bg-amber-500 py-2 text-sm font-bold text-black disabled:opacity-50"
        >
          {busy && !draft ? "Sto leggendo…" : "Chiedi a M.AI"}
        </button>

        {error ? (
          <p className="mt-2 text-xs text-red-400" role="alert">
            {error}
          </p>
        ) : null}
        {feedback ? (
          <p className="mt-2 text-xs text-emerald-400" role="status">
            {feedback}
          </p>
        ) : null}

        {draft ? (
          <div className="mt-4 border-t border-white/5 pt-4">
            {isDirectAnswer ? (
              <>
                <div className="mb-1 text-xs font-bold text-neutral-200">Risposta</div>
                <p className="text-sm leading-relaxed text-neutral-300">
                  {draft.answer ?? draft.preview.summary}
                </p>
                <button
                  type="button"
                  className="mt-3 text-xs text-neutral-500 underline"
                  onClick={() => setDraft(null)}
                >
                  Nuova domanda
                </button>
              </>
            ) : (
              <>
                <div className="mb-1 text-xs font-bold text-neutral-200">Anteprima</div>
                <p className="mb-2 text-sm text-amber-500">{draft.preview.summary}</p>
                {draft.preview.details && Object.keys(draft.preview.details).length > 0 ? (
                  <pre className="max-h-40 overflow-auto rounded bg-black/40 p-2 text-xs text-neutral-400">
                    {JSON.stringify(draft.preview.details, null, 2)}
                  </pre>
                ) : null}
                {(draft.preview.warnings?.length ?? 0) > 0 ? (
                  <div className="mt-2 text-xs text-amber-400">
                    {draft.preview.warnings.join(" · ")}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <button
                    type="button"
                    onClick={() => void confirm()}
                    disabled={busy || !draft.payload}
                    className="flex-1 rounded-lg bg-amber-500 py-2 text-sm font-bold text-black disabled:opacity-50"
                  >
                    Conferma
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraft(null)}
                    disabled={busy}
                    className="flex-1 rounded-lg border border-white/10 bg-white/5 py-2 text-sm text-neutral-300"
                  >
                    Annulla
                  </button>
                </div>
              </>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
