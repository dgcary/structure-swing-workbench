/** Reject incomplete or execution-capable payloads before showing account facts. */
const METRIC_KEYS = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
] as const;
const HOLDING_STATES = new Set(["snapshot", "partial", "unanchored", "conflict"]);
const CSV_KINDS = new Set(["account", "holdings", "fills"]);

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function optionalText(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function validMetric(value: unknown): boolean {
  if (!record(value) || typeof value.key !== "string" ||
      typeof value.label !== "string" || !value.label.trim() ||
      typeof value.unit !== "string" || !optionalText(value.value) ||
      !optionalText(value.source) || !optionalText(value.as_of)) return false;
  if (value.status === "available") {
    return typeof value.value === "string" && value.value.trim().length > 0 &&
      typeof value.source === "string" && value.source.trim().length > 0 &&
      typeof value.as_of === "string" && value.as_of.trim().length > 0;
  }
  return value.status === "unavailable" && value.value === null;
}

function validHolding(value: unknown): boolean {
  if (!record(value) || typeof value.symbol !== "string" || !value.symbol.trim() ||
      !HOLDING_STATES.has(String(value.status)) ||
      typeof value.warning !== "string" || !value.warning.trim()) return false;
  for (const key of ["quantity", "broker_display_cost", "core_quantity",
    "t_quantity", "source", "as_of"]) {
    if (!optionalText(value[key])) return false;
  }
  if (value.status === "conflict" || value.status === "unanchored") {
    return value.quantity === null;
  }
  return typeof value.quantity === "string" && value.quantity.trim().length > 0;
}

/** Both live and uploaded CSV overviews are read-only; neither authorizes trading. */
export function assertReadOnlyOverview(
  payload: unknown, mode: "read_only" | "isolated_csv_preview",
): void {
  const fail = (): never => { throw new Error("工作台数据协议异常；不可认定账户已核实或允许交易。"); };
  if (!record(payload)) fail();
  const metrics = Array.isArray(payload.metrics) ? payload.metrics : [];
  if (payload.mode !== mode ||
      payload.schema_version !== (mode === "read_only"
        ? "m8.overview.v1" : "m8.account_snapshot_preview.v1") ||
      payload.trade_execution_enabled !== false ||
      typeof payload.notice !== "string" || !payload.notice.trim() ||
      !Array.isArray(payload.metrics) || metrics.length !== METRIC_KEYS.length ||
      !metrics.every(validMetric) ||
      new Set(metrics.map((item: Record<string, unknown>) => item.key)).size !== METRIC_KEYS.length ||
      !METRIC_KEYS.every((key) => metrics.some(
        (item: Record<string, unknown>) => item.key === key,
      )) ||
      !(payload.holdings === null ||
        (Array.isArray(payload.holdings) && payload.holdings.every(validHolding))) ||
      payload.effective_plans !== null ||
      payload.pending_actions !== null ||
      payload.audit_results !== null) fail();

  if (mode === "isolated_csv_preview" &&
      (payload.persisted !== false || payload.realtime !== false ||
       payload.full_account_verified !== false ||
       payload.input_source !== "user_uploaded_csv" ||
       !Array.isArray(payload.imported_kinds) || !payload.imported_kinds.length ||
       payload.imported_kinds.some((kind: unknown) => !CSV_KINDS.has(String(kind))) ||
       new Set(payload.imported_kinds).size !== payload.imported_kinds.length)) fail();
}
