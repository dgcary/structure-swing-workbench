/** Typed fetch helpers and API response models for the workbench backend. */

export type EnumDto = { value: string; label: string };

export type PlanVersionFacts = {
  setup_type: EnumDto | null;
  structure_stage: EnumDto | null;
  structure_low_price: string | null;
  key_support_price: string | null;
  key_resistance_price: string | null;
  reversal_confirmed: boolean | null;
  structure_invalidated: boolean | null;
  structure_invalidation_price: string | null;
  structure_invalidation_condition: string | null;
  entry_mode: EnumDto | null;
  planned_total_position_amount: string | null;
  planned_total_position_pct: string | null;
  initial_entry_price_low: string | null;
  initial_entry_price_high: string | null;
  initial_entry_pct: string | null;
  confirmation_add_enabled: boolean | null;
  confirmation_trigger_price: string | null;
  confirmation_add_pct: string | null;
  t_reserve_pct: string | null;
  first_target_price: string | null;
  first_target_type: EnumDto | null;
  first_target_reduce_pct: string | null;
  remaining_exit_condition: string | null;
  remaining_exit_condition_triggered: boolean | null;
  valid_until: string | null;
};

export type AuditFindingDto = {
  rule: string;
  level: string;
  level_zh: string;
  message: string;
};

export type AuditResultDto = {
  id: string;
  level: EnumDto | null;
  summary: string;
  engine_version: string;
  details: {
    findings: AuditFindingDto[];
    skipped_rules: { rule: string; reason: string }[];
    account_equity: string | null;
  } | null;
  overrides: {
    id: string;
    reason: string;
    operator: string;
    created_at: string | null;
    revoked_at: string | null;
  }[];
  created_at: string | null;
};

export type PlanVersionDto = {
  id: string;
  plan_id: string;
  version_number: number;
  state: EnumDto | null;
  is_effective: boolean;
  version_reason: string | null;
  created_at: string | null;
  facts: PlanVersionFacts;
  audit_results?: AuditResultDto[];
};

export type PlanDto = {
  id: string;
  instrument_code: string;
  instrument_name: string;
  status: EnumDto | null;
  is_active: boolean;
  user_note: string | null;
  closed_at: string | null;
  created_at: string | null;
  effective_version_id: string | null;
  versions?: PlanVersionDto[];
};

export type PositionDto = {
  instrument_code: string;
  instrument_name: string;
  total_quantity: string | null;
  market_value: string | null;
  broker_cost_price: string | null;
  buckets: {
    bucket_type: EnumDto | null;
    quantity: string | null;
    strategy_cost_price: string | null;
    effective_cost_price: string | null;
    realized_t_pnl: string | null;
  }[];
};

export type SnapshotDto = {
  id: string;
  captured_at: string | null;
  total_equity: string | null;
  available_cash: string | null;
  source: string;
  positions: PositionDto[];
};

export type OverviewDto = {
  snapshot: SnapshotDto | null;
  active_plans: {
    id: string;
    instrument_code: string;
    instrument_name: string;
    status: EnumDto | null;
    risk_pct: string | null;
  }[];
  active_plan_count: number;
  total_risk_pct: string | null;
  position_count: number;
  current_positions: {
    instrument_code: string;
    instrument_name: string;
    baseline_quantity: string | null;
    net_fill_delta: string | null;
    current_quantity: string | null;
    as_of: string | null;
  }[];
};

export type TCycleDto = {
  t_cycle_key: string;
  instrument_code: string;
  instrument_name: string;
  day: string;
  status: string;
  matched_quantity: string | null;
  matched_gross_pnl: string | null;
  remaining_quantity: string | null;
  open_side: EnumDto | null;
  fill_count: number;
  action_ids: string[];
  exceeds_daily_limit: boolean;
};

export type PlanReviewDto = {
  plan: {
    id: string;
    instrument_code: string;
    instrument_name: string;
    status: EnumDto | null;
  };
  review: {
    total_buy_quantity: string | null;
    total_sell_quantity: string | null;
    avg_buy_price: string | null;
    avg_sell_price: string | null;
    remaining_quantity: string | null;
    realized_gross_pnl: string | null;
    first_fill_at: string | null;
    last_fill_at: string | null;
    holding_days: number | null;
    long_holding_note: string | null;
    entry_deviation_pct: string | null;
  };
  audit_summary: { level: EnumDto | null; count: number }[];
};

export type ActionDto = {
  id: string;
  action_type: EnumDto | null;
  side: EnumDto | null;
  status: EnumDto | null;
  planned_price_low: string | null;
  planned_price_high: string | null;
  planned_quantity: string | null;
  planned_position_pct: string | null;
  user_note: string | null;
  plan_version_id: string;
  version_number: number;
  plan: { id: string; instrument_code: string; instrument_name: string } | null;
};

export type ScreeningResultDto = {
  symbol: string;
  name: string;
  status: string;
  review_lane: string | null;
  reasons: { value: string; evidence: { source: string } }[];
  risk_facts: { code: string; state: string }[];
  missing_risk_checks: string[];
  messages: string[];
};

export type MarketResultDto = {
  value: Record<string, unknown> | Record<string, unknown>[] | null;
  source: string;
  fetched_at: string | null;
  observed_at: string | null;
  quality: string;
  missing_fields: string[];
  error: string | null;
};

const qualityNames: Record<string, string> = {
  FRESH: "新鲜",
  STALE: "过期",
  UNVERIFIED: "未校验",
  MISSING: "缺失",
  ERROR: "异常",
};

export const qualityName = (quality: string): string => qualityNames[quality] ?? quality;

const screeningStatusNames: Record<string, string> = {
  CANDIDATE: "候选",
  REVIEW: "待核实",
  EXCLUDED: "排除",
};

export const screeningStatusName = (status: string): string =>
  screeningStatusNames[status] ?? status;

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    const detail = payload.detail;
    return new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail));
  } catch {
    return new ApiError(`HTTP ${response.status}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; environment: string }>("/health"),
  overview: () => request<OverviewDto>("/account/overview"),
  listPlans: (activeOnly: boolean) =>
    request<PlanDto[]>(`/plans?active_only=${activeOnly ? "true" : "false"}`),
  getPlan: (planId: string) => request<PlanDto>(`/plans/${planId}`),
  createPlan: (body: unknown) => request<PlanDto>("/plans", { method: "POST", body: JSON.stringify(body) }),
  createRevision: (planId: string, body: unknown) =>
    request<PlanDto>(`/plans/${planId}/revisions`, { method: "POST", body: JSON.stringify(body) }),
  updateNote: (planId: string, userNote: string | null) =>
    request<PlanDto>(`/plans/${planId}/note`, { method: "PATCH", body: JSON.stringify({ user_note: userNote }) }),
  closePlan: (planId: string) => request<PlanDto>(`/plans/${planId}/close`, { method: "POST" }),
  submitVersion: (versionId: string) =>
    request<PlanVersionDto>(`/plan-versions/${versionId}/submit`, { method: "POST" }),
  runAudit: (versionId: string, accountEquity: string | null) =>
    request<AuditResultDto>(`/plan-versions/${versionId}/audit`, {
      method: "POST",
      body: JSON.stringify(accountEquity === null ? {} : { account_equity: accountEquity }),
    }),
  decideVersion: (versionId: string, body: { approve: boolean; user_confirmed?: boolean; override_reason?: string }) =>
    request<{ decision: { status: string } }>(`/plan-versions/${versionId}/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listActions: (status: string) => request<ActionDto[]>(`/actions?status=${status}`),
  screenCandidate: (body: unknown) =>
    request<ScreeningResultDto>("/candidates/screen", { method: "POST", body: JSON.stringify(body) }),
  marketQuote: (symbol: string) => request<MarketResultDto>(`/market/quote/${symbol}`),
  marketBars: (symbol: string, timeframe: string) =>
    request<MarketResultDto>(`/market/bars/${symbol}?timeframe=${encodeURIComponent(timeframe)}`),
  importCsv: (kind: string, data: string) =>
    request<{ duplicate: boolean; imported?: number; duplicates?: number; snapshot?: SnapshotDto; snapshots?: SnapshotDto[] }>(
      "/account/imports/csv",
      { method: "POST", body: JSON.stringify({ kind, data }) },
    ),
  listTCycles: (instrumentCode: string | null) =>
    request<TCycleDto[]>(instrumentCode ? `/t-cycles?instrument_code=${encodeURIComponent(instrumentCode)}` : "/t-cycles"),
  reviewPlan: (planId: string) => request<PlanReviewDto>(`/plans/${planId}/review`),
  parsePlanText: (text: string) =>
    request<{
      draft: {
        instrument_code: string | null;
        instrument_name: string | null;
        version_data: Record<string, unknown>;
      };
      warnings: string[];
    }>("/plans/parse", { method: "POST", body: JSON.stringify({ text }) }),
};
