/**
 * deevAI API client — fetch wrapper, token handling, typed responses.
 *
 * All requests go via Next.js rewrite at /api/v1/* → backend :8000.
 * This means no CORS in dev and easy deploy parity in prod.
 */

import { getStoredToken } from "./auth-store";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions extends RequestInit {
  noAuth?: boolean;
  query?: Record<string, string | number | undefined>;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { noAuth, query, headers, ...rest } = options;

  let url = `${API_BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) params.append(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string>),
  };
  if (!noAuth) {
    const token = getStoredToken();
    if (token) finalHeaders.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(url, { ...rest, headers: finalHeaders });

  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(`API ${res.status}`, res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return (await res.json()) as T;
}

// ── Typed endpoints ──────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  tenant_id: string;
  tenant_slug: string;
  expires_in_days: number;
}

export interface SignupBody {
  email: string;
  password: string;
  tenant_name: string;
  tenant_slug: string;
  full_name?: string;
}

export interface LoginBody {
  email: string;
  password: string;
}

export interface MessageResponse {
  message: string;
}

export const auth = {
  signup: (body: SignupBody) =>
    apiFetch<TokenResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(body),
      noAuth: true,
    }),
  login: (body: LoginBody) =>
    apiFetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
      noAuth: true,
    }),
  forgotPassword: (email: string) =>
    apiFetch<MessageResponse>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
      noAuth: true,
    }),
  resetPassword: (body: { token: string; password: string }) =>
    apiFetch<MessageResponse>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify(body),
      noAuth: true,
    }),
};

export interface IntegrationConnectResponse {
  integration_id: string;
  authorize_url: string;
}

export interface TenantRead {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  created_at: string;
}

export interface IntegrationRead {
  id: string;
  provider: string;
  name: string;
  status: string;
  // Per-provider bag (DV360 → {advertiser_id, partner_id}).
  provider_config: Record<string, unknown> | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// DV360 (Google Display & Video 360)
// ---------------------------------------------------------------------------

export interface Dv360ConnectBody {
  name: string;
  client_id: string;
  client_secret: string;
}

export interface Dv360AdvertiserRead {
  advertiser_id: string;
  display_name: string;
  partner_id: string | null;
  currency_code: string | null;
  timezone: string | null;
  entity_status: string | null;
}

export interface Dv360CallbackResult {
  integration_id: string;
  status: string;
  advertisers: Dv360AdvertiserRead[];
}

export interface Dv360SelectAdvertiserBody {
  advertiser_id: string;
  partner_id?: string;
}

export interface LineItemRead {
  id: string;
  advertiser_id: string;
  name: string;
  amazon_line_item_id: string;
  amazon_ad_group_id: string | null;
  amazon_bid_adjustment_rule_id: string | null;
  cpv_target: number;
  current_max_bid: number | null;
  mode: string;
  status: string;
}

export interface AdvertiserRead {
  id: string;
  integration_id: string;
  amazon_advertiser_id: string;
  name: string;
  currency: string;
  country: string;
  status: string;
}

export interface AdvertiserCreateBody {
  integration_id: string;
  amazon_advertiser_id: string;
  name: string;
  currency?: string;
  country?: string;
}

export interface LineItemCreateBody {
  advertiser_id: string;
  name: string;
  amazon_line_item_id: string;
  amazon_ad_group_id?: string;
  cpv_target: number;
  current_max_bid?: number;
  mode?: string;
}

export interface RunRead {
  id: string;
  line_item_id: string;
  week_label: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  blended_cpv_target: number | null;
  blended_cpv_observed: number | null;
  blended_visits: number | null;
  blended_spend: number | null;
  n_decisions: number;
  n_changes_proposed: number;
  n_changes_applied: number;
  digest_text: string | null;
  digest_generated_at: string | null;
  created_at: string;
}

export interface DecisionRead {
  id: string;
  run_id: string;
  targeting_module: string;
  targeting_key: string;
  value: string;
  field_label: string | null;
  previous_modifier: number;
  new_modifier: number;
  reason: string;
  note: string | null;
  observed_impressions: number | null;
  observed_clicks: number | null;
  observed_visits: number | null;
  observed_cpv: number | null;
  status: string;
}

export const tenants = {
  me: () => apiFetch<TenantRead>("/tenants/me"),
};

export const integrations = {
  connectDv360: (body: Dv360ConnectBody) =>
    apiFetch<IntegrationConnectResponse>("/integrations/dv360/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Called from /onboarding on mount when ?code & ?state are present
  // in the URL (Google has just redirected back).
  dv360Callback: (code: string, state: string) =>
    apiFetch<Dv360CallbackResult>(
      `/integrations/dv360/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
      { noAuth: true },
    ),
  selectDv360Advertiser: (
    integrationId: string,
    body: Dv360SelectAdvertiserBody,
  ) =>
    apiFetch<IntegrationRead>(
      `/integrations/${integrationId}/dv360/select-advertiser`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  list: () => apiFetch<IntegrationRead[]>("/integrations"),
};

export const advertisers = {
  list: () => apiFetch<AdvertiserRead[]>("/advertisers"),
  create: (body: AdvertiserCreateBody) =>
    apiFetch<AdvertiserRead>("/advertisers", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const lineItems = {
  list: () => apiFetch<LineItemRead[]>("/line-items"),
  create: (body: LineItemCreateBody) =>
    apiFetch<LineItemRead>("/line-items", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const runs = {
  list: (params?: { limit?: number; line_item_id?: string }) =>
    apiFetch<RunRead[]>("/runs", { query: params }),
  get: (runId: string) => apiFetch<RunRead>(`/runs/${runId}`),
  decisions: (runId: string) =>
    apiFetch<DecisionRead[]>(`/runs/${runId}/decisions`),
  updateDecision: (decisionId: string, status: "approved" | "rejected") =>
    apiFetch<DecisionRead>(`/runs/decisions/${decisionId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  trigger: (body: { line_item_id: string; language?: string }) =>
    apiFetch<RunRead>("/runs/trigger", {
      method: "POST",
      body: JSON.stringify({ language: "it", ...body }),
    }),
  apply: (runId: string, force = false) =>
    apiFetch<RunRead>(`/runs/${runId}/apply`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
};

export interface DigestGenerateBody {
  run_id?: string;
  language?: "it" | "en";
  previous_week_cpv?: number;
  previous_week_visits?: number;
}

export interface DigestResponse {
  run_id: string | null;
  week_label: string;
  language: string;
  text: string;
  generated_at: string;
  provider: string;
  cached: boolean;
}

export const digests = {
  generate: (body: DigestGenerateBody = {}) =>
    apiFetch<DigestResponse>("/digests/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export interface SettingRead {
  id: string;
  tenant_id: string;
  default_cpv_target: number;
  tolerance_band: number;
  max_step_per_run: number;
  max_modifier: number;
  min_modifier_active: number;
  exploration_revive_after_runs: number;
  exploration_revive_modifier: number;
  min_impressions_for_action: number;
  min_visits_for_strong_action: number;
  anomalous_ctr_threshold: number;
  min_viewability: number;
  observation_only_until: string | null;
  default_line_item_mode: "observation_only" | "approval_required" | "auto_apply";
  digest_language: "it" | "en";
  digest_delivery_email: boolean;
}

export interface SettingUpdate {
  default_cpv_target?: number;
  tolerance_band?: number;
  max_step_per_run?: number;
  max_modifier?: number;
  min_modifier_active?: number;
  exploration_revive_after_runs?: number;
  exploration_revive_modifier?: number;
  min_impressions_for_action?: number;
  min_visits_for_strong_action?: number;
  anomalous_ctr_threshold?: number;
  min_viewability?: number;
  default_line_item_mode?: "observation_only" | "approval_required" | "auto_apply";
  digest_language?: "it" | "en";
  digest_delivery_email?: boolean;
}

export const settingsApi = {
  get: () => apiFetch<SettingRead>("/settings"),
  update: (body: SettingUpdate) =>
    apiFetch<SettingRead>("/settings", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};
