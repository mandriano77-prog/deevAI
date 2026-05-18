"use client";

import type { AgentProposalRead } from "@/lib/api/proposals";

interface Props {
  proposal: AgentProposalRead;
  busy?: boolean;
  onApproveApply?: () => void;
  onReject?: () => void;
}

export function AgentProposalPanel({
  proposal,
  busy = false,
  onApproveApply,
  onReject,
}: Props) {
  return (
    <article className="rounded-lg border border-ink-800 bg-ink-900/80 p-5">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-ink-500">{proposal.agent_type}</p>
          <p className="mt-1 text-sm text-ink-100">{proposal.diagnosis ?? proposal.brief}</p>
        </div>
        <span className="rounded bg-ink-800 px-2 py-0.5 text-xs text-amber-300">{proposal.status}</span>
      </header>
      {proposal.proposed_changes.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-xs text-ink-300">
            <thead>
              <tr className="border-b border-ink-800 text-ink-500">
                <th className="py-2 pr-3 font-medium">Entità</th>
                <th className="py-2 pr-3 font-medium">Operazione</th>
                <th className="py-2 font-medium">Dettaglio</th>
              </tr>
            </thead>
            <tbody>
              {proposal.proposed_changes.map((ch, idx) => (
                <tr key={idx} className="border-b border-ink-900/80">
                  <td className="py-2 pr-3 text-ink-200">{ch.entity}</td>
                  <td className="py-2 pr-3">{ch.operation ?? ch.field ?? "—"}</td>
                  <td className="py-2 font-mono text-ink-400">
                    {ch.payload
                      ? JSON.stringify(ch.payload).slice(0, 120)
                      : `${String(ch.from ?? "")} → ${String(ch.to ?? "")}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-xs text-ink-500">Nessuna modifica proposta.</p>
      )}
      <div className="mt-4 flex gap-2">
        {onApproveApply ? (
          <button
            type="button"
            disabled={busy || proposal.status !== "pending"}
            className="rounded bg-amber-600 px-3 py-1.5 text-xs font-medium text-ink-950 disabled:opacity-50"
            onClick={onApproveApply}
          >
            Approva e applica
          </button>
        ) : null}
        {onReject ? (
          <button
            type="button"
            disabled={busy || proposal.status !== "pending"}
            className="rounded bg-ink-800 px-3 py-1.5 text-xs text-ink-300 disabled:opacity-50"
            onClick={onReject}
          >
            Rifiuta
          </button>
        ) : null}
      </div>
    </article>
  );
}
