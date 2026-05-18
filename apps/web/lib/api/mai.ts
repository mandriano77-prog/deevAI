/**
 * M.AI — conversational orchestration (camelCase JSON via ApiModel).
 */

import { apiFetch } from "../api";

export type MaiResponseType = "query" | "brief" | "govern" | "system";

export interface MaiAskResponse {
  intent: string;
  type: MaiResponseType;
  preview: {
    summary: string;
    details: Record<string, unknown>;
    warnings: string[];
  };
  payload?: Record<string, unknown>;
  answer?: string;
}

export interface MaiExecuteResponse {
  success: boolean;
  message: string;
  data?: Record<string, unknown>;
}

export interface MaiLogItem {
  id: string;
  lineItemId: string | null;
  prompt: string | null;
  intent: string | null;
  action: string;
  proposal?: Record<string, unknown> | null;
  payload?: Record<string, unknown> | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  createdAt: string;
}

export const maiApi = {
  ask: (prompt: string, lineItemId: string) =>
    apiFetch<MaiAskResponse>("/mai/ask", {
      method: "POST",
      body: JSON.stringify({ prompt, lineItemId }),
    }),

  execute: (intent: string, payload: Record<string, unknown>) =>
    apiFetch<MaiExecuteResponse>("/mai/execute", {
      method: "POST",
      body: JSON.stringify({ intent, payload }),
    }),

  history: (params?: { lineItemId?: string; limit?: number }) =>
    apiFetch<{ items: MaiLogItem[] }>("/mai/history", {
      query: params,
    }),
};
