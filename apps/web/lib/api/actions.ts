import { apiFetch } from "../api";

export interface ActionRead {
  id: string;
  tenant_id: string;
  line_item_id: string | null;
  name: string;
  type: string;
  weight: number;
  value_eur: number;
  value_source: string;
  value_currency: string;
  tracking_source: string;
  attribution_window_hours: number;
  dedupe_rule: string;
  quality_filter: Record<string, unknown> | null;
  funnel_parent_id: string | null;
  funnel_position: number | null;
  status: string;
}

export interface ActionCreate {
  name: string;
  type?: string;
  weight?: number;
  value_eur?: number;
  line_item_id?: string | null;
}

export interface ActionUpdate {
  name?: string;
  type?: string;
  weight?: number;
  value_eur?: number;
  status?: string;
}

export const actionsApi = {
  list: () => apiFetch<ActionRead[]>("/actions"),
  funnel: () => apiFetch<ActionRead[]>("/actions/funnel"),
  create: (body: ActionCreate) =>
    apiFetch<ActionRead>("/actions", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: ActionUpdate) =>
    apiFetch<ActionRead>(`/actions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: string) =>
    apiFetch<void>(`/actions/${id}`, { method: "DELETE" }),
  setFunnel: (ordered_action_ids: string[]) =>
    apiFetch<ActionRead[]>("/actions/funnel", {
      method: "POST",
      body: JSON.stringify({ ordered_action_ids }),
    }),
};
