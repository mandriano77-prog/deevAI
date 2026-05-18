import { apiFetch } from "../api";

export interface OptimizationStrategyRead {
  id: string;
  tenant_id: string;
  line_item_id: string | null;
  mode: string;
  primary_metric: string;
  primary_target: number;
  primary_weight: number;
  secondary_metric: string | null;
  secondary_target: number | null;
  secondary_weight: number | null;
  tertiary_metric: string | null;
  tertiary_target: number | null;
  tertiary_weight: number | null;
  primary_action_id: string | null;
  tolerance_band: number;
  status: string;
}

export interface OptimizationStrategyUpsert {
  mode?: string;
  primary_metric?: string;
  primary_target: number;
  primary_weight?: number;
  secondary_metric?: string | null;
  secondary_target?: number | null;
  secondary_weight?: number | null;
  tertiary_metric?: string | null;
  tertiary_target?: number | null;
  tertiary_weight?: number | null;
  tolerance_band?: number;
}

export interface HardConstraintRead {
  id: string;
  tenant_id: string;
  optimization_strategy_id: string;
  metric: string;
  operator: string;
  value: number;
  violation_policy: string;
  status: string;
}

export interface HardConstraintCreate {
  metric: string;
  operator: string;
  value: number;
  violation_policy?: string;
}

export const optimizationApi = {
  getDefault: () =>
    apiFetch<OptimizationStrategyRead>("/optimization-strategies/default"),
  upsertDefault: (body: OptimizationStrategyUpsert) =>
    apiFetch<OptimizationStrategyRead>("/optimization-strategies/default", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  listConstraints: (strategyId: string) =>
    apiFetch<HardConstraintRead[]>(
      `/optimization-strategies/${strategyId}/constraints`,
    ),
  createConstraint: (strategyId: string, body: HardConstraintCreate) =>
    apiFetch<HardConstraintRead>(
      `/optimization-strategies/${strategyId}/constraints`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  deleteConstraint: (constraintId: string) =>
    apiFetch<void>(`/constraints/${constraintId}`, { method: "DELETE" }),
};
