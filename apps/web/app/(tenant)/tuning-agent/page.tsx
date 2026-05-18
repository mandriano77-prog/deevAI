"use client";

import { useEffect, useState } from "react";

import { AgentProposalPanel } from "@/components/agent-proposal-panel";
import { Topbar } from "@/components/topbar";
import { proposalsApi, tuningAgentApi, type AgentProposalRead } from "@/lib/api/proposals";

const DEMO_LINE_ITEM_ID = process.env.NEXT_PUBLIC_DEMO_LINE_ITEM_ID ?? "";

export default function TuningAgentPage() {
  const [brief, setBrief] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<AgentProposalRead[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void proposalsApi.list({ agent_type: "tuning" }).then(setHistory).catch(() => {});
  }, []);

  async function submit() {
    if (!DEMO_LINE_ITEM_ID) {
      setError("Imposta NEXT_PUBLIC_DEMO_LINE_ITEM_ID");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const p = await tuningAgentApi.brief(DEMO_LINE_ITEM_ID, brief);
      setHistory((h) => [p, ...h].slice(0, 10));
      setBrief("");
    } catch {
      setError("Brief non elaborato");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Topbar title="Tuning agent" subtitle="Micro-aggiustamenti operativi" />
      <main className="mx-auto max-w-2xl space-y-6 p-8">
        <textarea
          className="w-full rounded-md border border-ink-700 bg-ink-900 p-3 text-sm text-ink-50"
          rows={4}
          placeholder="Es. CPA alto ma volume ok"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          aria-label="Brief tuning"
        />
        <button
          type="button"
          disabled={loading || brief.length < 3}
          className="rounded-md bg-amber-600 px-4 py-2 text-sm text-ink-950 disabled:opacity-50"
          onClick={() => void submit()}
        >
          {loading ? "Analizzo…" : "Invia brief"}
        </button>
        {error ? <p className="text-sm text-red-300" role="alert">{error}</p> : null}
        <section aria-labelledby="history-heading" className="space-y-3">
          <h2 id="history-heading" className="text-sm font-medium text-ink-50">
            Ultime proposte
          </h2>
          {history.length === 0 ? (
            <p className="text-xs text-ink-500">Nessuna proposta ancora.</p>
          ) : (
            history.map((p) => (
              <AgentProposalPanel key={p.id} proposal={p} />
            ))
          )}
        </section>
      </main>
    </div>
  );
}
