import { validObservedAt } from "./validObservedAt.ts";

/** Reject incomplete or execution-capable payloads before showing account facts. */
const METRIC_KEYS = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
] as const;
const HOLDING_STATES = new Set(["snapshot", "partial", "unanchored", "conflict"]);
const CSV_KINDS = new Set(["account", "holdings", "fills"]);
// A-share symbols must be six digits, optionally with an explicit exchange.
const A_SHARE_SYMBOL = /^(?:\d{6}(?:\.(?:SH|SZ|BJ))?|(?:SH|SZ|BJ)\d{6})$/;
const COUNT_METRICS = new Set(["position_count", "t_cycles_today", "open_t_cycles"]);
const TEXT_METRICS = new Set(["rotation_status", "highest_audit"]);

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function optionalText(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

/** Accept finite decimal/scientific quantities only; JS Number also parses hex/binary. */
function decimalText(value: unknown, allowNegative = false): value is string {
  if (typeof value !== "string" ||
      !/^-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return false;
  const number = Number(value);
  return Number.isFinite(number) && (allowNegative || number >= 0);
}

function validMetric(value: unknown): boolean {
  if (!record(value) || typeof value.key !== "string" ||
      typeof value.label !== "string" || !value.label.trim() ||
      typeof value.unit !== "string" || !optionalText(value.value) ||
      !optionalText(value.source) || !optionalText(value.as_of)) return false;
  if (value.status === "available") {
    if (typeof value.value !== "string" || !value.value.trim() ||
        typeof value.source !== "string" || !value.source.trim() ||
        typeof value.as_of !== "string" ||
        !validObservedAt(value.as_of)) return false;
    if (TEXT_METRICS.has(value.key)) return true;
    // A string like "0x10" is accepted by Number(), but is not a broker decimal.
    if (!decimalText(value.value)) return false;
    const numeric = Number(value.value);
    if (COUNT_METRICS.has(value.key) && !Number.isSafeInteger(numeric)) return false;
    if (value.key === "position_ratio" && numeric > 100) return false;
    return true;
  }
  // Missing values must not carry a supposedly verified source or timestamp.
  return value.status === "unavailable" && value.value === null &&
    value.source === null && value.as_of === null;
}

function validHolding(value: unknown): boolean {
  if (!record(value) || typeof value.symbol !== "string" || !A_SHARE_SYMBOL.test(value.symbol) ||
      !HOLDING_STATES.has(String(value.status)) ||
      typeof value.warning !== "string" || !value.warning.trim()) return false;
  for (const key of ["quantity", "broker_display_cost", "core_quantity",
    "t_quantity", "source", "as_of"]) {
    if (!optionalText(value[key])) return false;
  }
  for (const key of ["core_quantity", "t_quantity"]) {
    const quantity = value[key];
    if (quantity !== null &&
        (!decimalText(quantity))) return false;
  }
  if (value.broker_display_cost !== null &&
      (!decimalText(value.broker_display_cost, true))) return false;
  // These optional details are displayed as confirmed fills and net changes.
  // Validate them before rendering; never present malformed data as verified.
  if (value.applied_fill_ids !== undefined &&
      (!Array.isArray(value.applied_fill_ids) ||
       !value.applied_fill_ids.every((id: unknown) =>
         typeof id === "string" && id.trim().length > 0) ||
       new Set(value.applied_fill_ids).size !== value.applied_fill_ids.length)) return false;
  if (value.unanchored_fill_delta !== undefined &&
      value.unanchored_fill_delta !== null &&
      (!decimalText(value.unanchored_fill_delta, true))) return false;
  if (value.status !== "unanchored" &&
      value.unanchored_fill_delta != null) return false;
  if (typeof value.source !== "string" || !value.source.trim() ||
      typeof value.as_of !== "string" ||
      !validObservedAt(value.as_of)) return false;
  if (value.status === "conflict" || value.status === "unanchored") {
    // A fill delta or contradictory snapshot cannot establish cost or core/T allocations.
    return value.quantity === null && value.broker_display_cost === null &&
      value.core_quantity === null && value.t_quantity === null;
  }
  if (!decimalText(value.quantity)) return false;
  if (value.status === "partial" && value.broker_display_cost !== null) return false;
  if (value.status === "snapshot" && value.broker_display_cost === null) return false;
  // Prevent presenting allocations larger than the sourced, anchored holding.
  const core = value.core_quantity === null ? 0 : Number(value.core_quantity);
  const t = value.t_quantity === null ? 0 : Number(value.t_quantity);
  const total = Number(value.quantity);
  if (core + t > total + Math.max(1, total) * Number.EPSILON * 4) return false;
  return true;
}

/** Both live and uploaded CSV overviews are read-only; neither authorizes trading. */
export function assertReadOnlyOverview(
  payload: unknown, mode: "read_only" | "isolated_csv_preview",
): void {
  const fail = (): never => { throw new Error("工作台数据协议异常；不可认定账户已核实或允许交易。"); };
  if (!record(payload)) fail();
  const data = payload as Record<string, unknown>;
  const metrics = Array.isArray(data.metrics) ? data.metrics : [];
  const kinds = Array.isArray(data.imported_kinds) ? data.imported_kinds : [];
  if (data.mode !== mode ||
      data.schema_version !== (mode === "read_only"
        ? "m8.overview.v1" : "m8.account_snapshot_preview.v1") ||
      data.trade_execution_enabled !== false ||
      typeof data.notice !== "string" || !data.notice.trim() ||
      !Array.isArray(data.metrics) || metrics.length !== METRIC_KEYS.length ||
      !metrics.every(validMetric) ||
      new Set(metrics.map((item: Record<string, unknown>) => item.key)).size !== METRIC_KEYS.length ||
      !METRIC_KEYS.every((key) => metrics.some(
        (item: Record<string, unknown>) => item.key === key,
      )) ||
      !(data.holdings === null ||
        (Array.isArray(data.holdings) && data.holdings.length > 0 &&
         data.holdings.every(validHolding) &&
         new Set(data.holdings.map((holding: Record<string, unknown>) =>
           String(holding.symbol).trim())).size === data.holdings.length)) ||
      data.effective_plans !== null ||
      data.pending_actions !== null ||
      data.audit_results !== null) fail();

  if (mode === "isolated_csv_preview" &&
      (data.persisted !== false || data.realtime !== false ||
       data.full_account_verified !== false ||
       data.input_source !== "user_uploaded_csv" ||
       !Array.isArray(data.imported_kinds) || !kinds.length ||
       kinds.some((kind: unknown) => !CSV_KINDS.has(String(kind))) ||
       new Set(kinds).size !== kinds.length)) fail();
}
