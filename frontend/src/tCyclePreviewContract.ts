/** Fail closed when a T preview could misstate the cycle or its provenance. */
export type TCyclePreviewInput = {
  symbol: string;
  direction: "positive" | "reverse";
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
