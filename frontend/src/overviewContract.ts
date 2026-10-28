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

/** Accept finite decimal/scientific quantities, rejecting nonzero underflow. */
function decimalText(value: unknown, allowNegative = false): value is string {
  if (typeof value !== "string" || value.length > 128 ||
      !/^-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return false;
  const exponent = Number(value.split(/[eE]/)[1] ?? "0");
  if (!Number.isFinite(exponent) || Math.abs(exponent) > 308) return false;
  const number = Number(value);
  const mantissa = value.split(/[eE]/)[0];
  // Number("1e-999") is zero; never let a nonzero sourced fact become zero.
  return Number.isFinite(number) &&
    (number !== 0 || !/[1-9]/.test(mantissa)) &&
    (allowNegative || number >= 0);
}

/** Exact decimal arithmetic for inventory and integer-count checks. */
function decimalParts(value: string): { digits: bigint; power: number } {
  const match = /^(-?)(?:(\d+)(?:\.(\d+))?|\.(\d+))(?:[eE]([+-]?\d+))?$/.exec(value);
  if (!match) throw new Error("无效十进制数值");
  const fraction = match[3] ?? match[4] ?? "";
  const digits = BigInt((match[2] ?? "0") + fraction);
  return {
    digits: match[1] === "-" ? -digits : digits,
    power: Number(match[5] ?? "0") - fraction.length,
  };
}

function exactInteger(value: string): boolean {
  const { digits, power } = decimalParts(value);
  return power >= 0 || digits % (10n ** BigInt(-power)) === 0n;
}

function allocationWithinHolding(core: string, t: string, total: string): boolean {
  const parts = [core, t, total].map(decimalParts);
  const minPower = Math.min(...parts.map((part) => part.power));
  const scaled = parts.map(({ digits, power }) =>
    digits * (10n ** BigInt(power - minPower)));
  return scaled[0] + scaled[1] <= scaled[2];
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
    if (COUNT_METRICS.has(value.key) &&
        (!Number.isSafeInteger(numeric) || !exactInteger(value.value))) return false;
    // §15.48: a sourced historical snapshot can legitimately show >100%
    // gross exposure. Never hide an over-limit value at the UI boundary.
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
  // Never use floating-point tolerance for sourced share allocations:
  // tiny quantities and values above 2^53 can otherwise hide an over-allocation.
  if (!allocationWithinHolding(
    (value.core_quantity as string | null) ?? "0",
    (value.t_quantity as string | null) ?? "0",
    value.quantity as string,
  )) return false;
  return true;
}


/** Persisted records are display-only and must never be accepted from a CSV preview. */
function sourcedRow(value: unknown, prefix: string): value is Record<string, unknown> {
  return record(value) && typeof value.id === "string" && value.id.trim().length > 0 &&
    typeof value.source === "string" && value.source.startsWith(prefix) &&
    (value.as_of === null || validObservedAt(value.as_of));
}

function optionalDecimal(value: unknown): boolean {
  return value === null || decimalText(value);
}

function validPlanRow(value: unknown): boolean {
  return sourcedRow(value, "正式计划版本/") &&
    typeof value.symbol === "string" && A_SHARE_SYMBOL.test(value.symbol) &&
    typeof value.name === "string" && value.name.trim().length > 0 &&
    typeof value.version === "number" && Number.isSafeInteger(value.version) &&
    value.version > 0 && typeof value.state_zh === "string" &&
    value.state_zh.trim().length > 0 &&
    ["invalidation_price", "first_target_price", "initial_risk", "current_risk",
       "historical_cost_risk_estimate"]
      .every((key) => optionalDecimal(value[key])) &&
    typeof value.warning === "string" && value.warning.trim().length > 0;
}

function validCalendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(value + "T00:00:00Z");
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function validActionRow(value: unknown): boolean {
  return sourcedRow(value, "正式交易动作/") &&
    typeof value.symbol === "string" && A_SHARE_SYMBOL.test(value.symbol) &&
    typeof value.action_zh === "string" && value.action_zh.trim().length > 0 &&
    typeof value.status_zh === "string" && value.status_zh.trim().length > 0 &&
    optionalDecimal(value.planned_price_low) &&
    optionalDecimal(value.planned_price_high) &&
    (value.date_status === "unverified"
      ? value.planned_for_date === null
      : (value.date_status === "today" || value.date_status === "other_day") &&
        value.as_of !== null && validCalendarDate(value.planned_for_date)) &&
    value.executable === false &&
    typeof value.warning === "string" && value.warning.trim().length > 0;
}

function validAuditRow(value: unknown): boolean {
  return sourcedRow(value, "审计记录/") &&
    typeof value.level === "string" &&
    ["pass", "warning", "overridable_fail", "hard_fail"].includes(value.level) &&
    typeof value.level_zh === "string" && value.level_zh.trim().length > 0 &&
    typeof value.summary === "string" && value.summary.trim().length > 0 &&
    value.executable === false &&
    typeof value.warning === "string" && value.warning.trim().length > 0;
}

/** Recorded T legs are partial evidence, never a broker-complete daily count. */
function validRecordedTCycle(value: unknown): boolean {
  if (!record(value) || typeof value.symbol !== "string" ||
      !A_SHARE_SYMBOL.test(value.symbol) ||
      !optionalText(value.cycle_key) || !optionalText(value.plan_version_id) ||
      !validCalendarDate(value.market_date) ||
      !["open", "closed", "conflict"].includes(String(value.state)) ||
      !(value.direction === null || value.direction === "positive" ||
        value.direction === "reverse") ||
      !optionalText(value.opening_quantity) ||
      !optionalText(value.closing_quantity) ||
      !optionalText(value.residual_quantity) ||
      !optionalText(value.ordinary_effect) ||
      !optionalText(value.as_of) ||
      typeof value.end_of_day_unclosed !== "boolean" ||
      typeof value.requires_reaudit !== "boolean" ||
      !(value.recorded_daily_limit_alert === null ||
        value.recorded_daily_limit_alert === true) ||
      value.broker_reconciled !== false ||
      value.trade_execution_enabled !== false ||
      typeof value.warning !== "string" || !value.warning.trim() ||
      !Array.isArray(value.sources) || value.sources.length === 0 ||
      !value.sources.every((source: unknown) =>
        typeof source === "string" && source.startsWith("成交记录/") &&
        source.length > "成交记录/".length)) return false;
  if (value.as_of !== null && !validObservedAt(value.as_of)) return false;
  if (value.state === "conflict") {
    if (value.opening_quantity !== null || value.closing_quantity !== null ||
        value.end_of_day_unclosed || value.requires_reaudit) return false;
  } else {
    if (value.direction === null || value.as_of === null ||
        !decimalText(value.opening_quantity) ||
        !decimalText(value.closing_quantity)) return false;
    const opening = decimalParts(value.opening_quantity);
    const closing = decimalParts(value.closing_quantity);
    const minPower = Math.min(opening.power, closing.power);
    const openUnits = opening.digits * 10n ** BigInt(opening.power - minPower);
    const closeUnits = closing.digits * 10n ** BigInt(closing.power - minPower);
    if (openUnits <= 0n || closeUnits < 0n ||
        (value.state === "closed" && closeUnits !== openUnits) ||
        (value.state === "open" && closeUnits >= openUnits)) return false;
    if (value.end_of_day_unclosed) {
      if (value.state !== "open" || !value.requires_reaudit ||
          !decimalText(value.residual_quantity) ||
          value.ordinary_effect !== (value.direction === "positive"
            ? "普通减仓待核验" : "普通加仓待核验")) return false;
      const residual = decimalParts(value.residual_quantity);
      const p = Math.min(opening.power, closing.power, residual.power);
      if (residual.digits * 10n ** BigInt(residual.power - p) !==
          openUnits * 10n ** BigInt(minPower - p) -
          closeUnits * 10n ** BigInt(minPower - p)) return false;
    }
  }
  if (!value.end_of_day_unclosed &&
      (value.requires_reaudit || value.residual_quantity !== null ||
       value.ordinary_effect !== null)) return false;
  return true;
}

function validPersistedSections(
  data: Record<string, unknown>, mode: "read_only" | "isolated_csv_preview",
): boolean {
  const keys = ["effective_plans", "pending_actions", "audit_results"] as const;
  if (mode === "isolated_csv_preview") return keys.every((key) => data[key] === null);
  if (keys.every((key) => data[key] === null)) return true;
  const validators = [validPlanRow, validActionRow, validAuditRow];
  return keys.every((key, index) => {
    const rows = data[key];
    return Array.isArray(rows) && rows.every(validators[index]) &&
      new Set(rows.map((row: Record<string, unknown>) => row.id)).size === rows.length;
  });
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
      !validPersistedSections(data, mode) ||
      (data.t_cycle_evidence !== undefined &&
        !(mode === "isolated_csv_preview"
          ? data.t_cycle_evidence === null
          : data.t_cycle_evidence === null ||
            (Array.isArray(data.t_cycle_evidence) &&
             data.t_cycle_evidence.every(validRecordedTCycle))))) fail();

  // The source is partial, but three or more distinct recorded closed pairs
  // for one symbol/day must trigger a lower-bound warning on every row.
  // Fewer than three is NOT proof that the trading rule passed.
  if (Array.isArray(data.t_cycle_evidence)) {
    const closedByDay = new Map<string, number>();
    for (const cycle of data.t_cycle_evidence) {
      const key = cycle.symbol + "/" + cycle.market_date;
      if (cycle.state === "closed") {
        closedByDay.set(key, (closedByDay.get(key) ?? 0) + 1);
      }
    }
    if (data.t_cycle_evidence.some((cycle: Record<string, unknown>) =>
      ((closedByDay.get(String(cycle.symbol) + "/" + String(cycle.market_date)) ?? 0) > 2)
      !== (cycle.recorded_daily_limit_alert === true))) fail();
  }

  if (mode === "isolated_csv_preview" &&
      (data.persisted !== false || data.realtime !== false ||
       data.full_account_verified !== false ||
       data.input_source !== "user_uploaded_csv" ||
       !Array.isArray(data.imported_kinds) || !kinds.length ||
       kinds.some((kind: unknown) => !CSV_KINDS.has(String(kind))) ||
       new Set(kinds).size !== kinds.length)) fail();
}
