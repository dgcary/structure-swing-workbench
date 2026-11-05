/** Fail closed when a T preview could misstate the cycle or its provenance. */
export type TCyclePreviewInput = {
  symbol: string;
  direction: "positive" | "reverse";
  expectRisk?: boolean;
};
export type TCyclePreviewResult = {
  schema_version: "m8.t_cycle_preview.v1";
  symbol: string;
  direction: "positive" | "reverse";
  cycle_status: "open" | "closed";
  remaining_quantity: string;
  realized_gross_pnl: string | null;
  pending_matched_gross_pnl: string | null;
  notice: string;
  projected_risk: null | {
    projected_max_loss: string;
    projected_account_risk_pct: string; // One security/plan as % of account equity
    account_total_max_loss: string; // Across stocks: display only, never a tier
    account_total_risk_pct: string;
    other_positions_max_loss: string;
    existing_t_max_loss: string;
    core_max_loss: string;
    new_t_max_loss: string;
    level: "PASS" | "WARNING" | "HARD_FAIL";
    verified: false;
    source: string;
    warning: string;
  };
  persisted: false;
  broker_reconciled: false;
  daily_cycle_limit_verified: false;
  trade_execution_enabled: false;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function finiteAmount(value: unknown, nonnegative: boolean): value is string {
  return typeof value === "string" && value.trim() !== "" &&
    Number.isFinite(Number(value)) && (!nonnegative || Number(value) >= 0);
}

/** Validate all user-visible fields before showing a calculated T result. */
export function assertTCyclePreview(
  payload: unknown, input: TCyclePreviewInput,
): asserts payload is TCyclePreviewResult {
  const fail = (): never => {
    throw new Error("T仓预览数据协议异常；未展示未核实的循环或盈亏。");
  };
  if (!isRecord(payload)) fail();
  const data = payload as Record<string, unknown>;
  if (data.schema_version !== "m8.t_cycle_preview.v1" ||
      data.symbol !== input.symbol || data.direction !== input.direction ||
      data.persisted !== false || data.broker_reconciled !== false ||
      data.daily_cycle_limit_verified !== false ||
      data.trade_execution_enabled !== false ||
      typeof data.notice !== "string" || !data.notice.trim() ||
      !finiteAmount(data.remaining_quantity, true)) fail();
  if (data.projected_risk === null) {
    if (input.expectRisk) fail();
  } else {
    if (!input.expectRisk || input.direction !== "reverse" ||
        !isRecord(data.projected_risk)) fail();
    const risk = data.projected_risk as Record<string, unknown>;
    if (risk.verified !== false ||
        typeof risk.source !== "string" || !risk.source.trim() ||
        typeof risk.warning !== "string" || !risk.warning.trim() ||
        !finiteAmount(risk.projected_max_loss, true) ||
        !finiteAmount(risk.projected_account_risk_pct, true) ||
        !finiteAmount(risk.account_total_max_loss, true) ||
        !finiteAmount(risk.account_total_risk_pct, true) ||
        !finiteAmount(risk.other_positions_max_loss, true) ||
        !finiteAmount(risk.existing_t_max_loss, true) ||
        !finiteAmount(risk.core_max_loss, true) ||
        !finiteAmount(risk.new_t_max_loss, true)) fail();
    const pct = Number(risk.projected_account_risk_pct);
    const planLoss = Number(risk.projected_max_loss);
    const totalLoss = Number(risk.account_total_max_loss);
    const otherLoss = Number(risk.other_positions_max_loss);
    const existingTLoss = Number(risk.existing_t_max_loss);
    const expectedPlanLoss = Number(risk.core_max_loss) +
      Number(risk.new_t_max_loss) + existingTLoss;
    const near = (a: number, b: number) =>
      Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
    if (!near(planLoss, expectedPlanLoss) ||
        !near(totalLoss, planLoss + otherLoss) ||
        !near(Number(risk.account_total_risk_pct) * planLoss, pct * totalLoss)) fail();
    const expectedLevel = pct <= 2 ? "PASS" : pct <= 3 ? "WARNING" : "HARD_FAIL";
    if (risk.level !== expectedLevel) fail();
  }
  if (data.cycle_status === "closed") {
    if (Number(data.remaining_quantity) !== 0 ||
        !finiteAmount(data.realized_gross_pnl, false) ||
        data.pending_matched_gross_pnl !== null) fail();
  } else if (data.cycle_status === "open") {
    if (Number(data.remaining_quantity) <= 0 ||
        data.realized_gross_pnl !== null ||
        !finiteAmount(data.pending_matched_gross_pnl, false)) fail();
  } else fail();
}
