"use client";

import { useState } from "react";

import { AgentProposalPanel } from "@/components/agent-proposal-panel";
import { Topbar } from "@/components/topbar";
import { proposalsApi, setupAgentApi, type AgentProposalRead } from "@/lib/api/proposals";

const DEMO_LINE_ITEM_ID = process.env.NEXT_PUBLIC_DEMO_LINE_ITEM_ID ?? "";

export default function SetupAgentPage() {
  const [brief, setBrief] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<AgentProposalRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!DEMO_LINE_ITEM_ID) {
      setError("Imposta NEXT_PUBLIC_DEMO_LINE_ITEM_ID per la demo");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const p = await setupAgentApi.brief(DEMO_LINE_ITEM_ID, brief);
      setProposal(p);
    } catch {
      setError("Generazione non riuscita");
    } finally {
      setLoading(false);
    }
  }

  async function approveAndApply() {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const approved = await proposalsApi.approve(proposal.id);
      const applied = await proposalsApi.apply(approved.id);
      setProposal(applied);
    } catch {
      setError("Approvazione o apply non riusciti");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <Topbar title="Setup agent" subtitle="Configurazione completa da brief" />
      <main className="mx-auto max-w-3xl space-y-6 p-8">
        <label className="block text-sm text-ink-200">
          Brief libero
          <textarea
            className="mt-2 min-h-[160px] w-full rounded-md border border-ink-700 bg-ink-900 p-3 text-ink-50"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            aria-label="Brief setup agent"
          />
        </label>
        <button
          type="button"
          disabled={loading || brief.length < 3}
          className="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-ink-950 disabled:opacity-50"
          onClick={() => void submit()}
        >
          {loading ? "Analizzo il tuo business…" : "Genera configurazione"}
        </button>
        {error ? <p className="text-sm text-red-300" role="alert">{error}</p> : null}
        {proposal ? (
          <AgentProposalPanel
            proposal={proposal}
            busy={busy}
            onApproveApply={() => void approveAndApply()}
            onReject={() =>
              void proposalsApi.reject(proposal.id).then((p) => setProposal(p))
            }
          />
        ) : null}
      </main>
    </div>
  );
}
