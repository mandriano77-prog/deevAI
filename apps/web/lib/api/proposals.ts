import { apiFetch } from "../api";

export interface AgentProposalRead {
  id: string;
  agent_type: string;
  brief: string;
  diagnosis: string | null;
  proposed_changes: Array<{
    entity: string;
    operation?: string;
    field?: string;
    from?: unknown;
    to?: unknown;
    payload?: Record<string, unknown>;
  }>;
  expected_impact: Record<string, unknown> | null;
  status: string;
  auto_applicable: boolean;
  post_mortem: Record<string, unknown> | null;
}

export const proposalsApi = {
  list: (params?: { agent_type?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.agent_type) q.set("agent_type", params.agent_type);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return apiFetch<AgentProposalRead[]>(`/proposals${qs ? `?${qs}` : ""}`);
  },
  approve: (id: string) =>
    apiFetch<AgentProposalRead>(`/proposals/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    apiFetch<AgentProposalRead>(`/proposals/${id}/reject`, { method: "POST" }),
  apply: (id: string) =>
    apiFetch<AgentProposalRead>(`/proposals/${id}/apply`, { method: "POST" }),
};

export const setupAgentApi = {
  brief: (lineItemId: string, brief: string) =>
    apiFetch<AgentProposalRead>(`/line-items/${lineItemId}/setup-agent/brief`, {
      method: "POST",
      body: JSON.stringify({ brief }),
    }),
};

export const tuningAgentApi = {
  brief: (lineItemId: string, brief: string) =>
    apiFetch<AgentProposalRead>(`/line-items/${lineItemId}/tuning-agent/brief`, {
      method: "POST",
      body: JSON.stringify({ brief }),
    }),
};
