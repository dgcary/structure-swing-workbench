export type DongwuStatementCheck = {
  schema_version: "m8.dongwu_statement_check.v1";
  mode: "local_pdf_preview";
  notice: string;
  status: "matched_unverified" | "mismatch";
  period_start: string;
  period_end: string;
  summary_row_count: number;
  detail_row_count: number;
  matched_group_count: number;
  missing_summary_group_count: number;
  extra_summary_group_count: number;
  mismatched_group_count: number;
  repaired_summary_rows: number;
  broker_reconciled: false;
  full_account_verified: false;
  trade_execution_enabled: false;
  execution_ids_available: false;
  execution_times_available: false;
  footer_totals_checked: true;
  footer_totals_mismatched_count: number;
};

// Do not route private PDF bytes through the configurable Web /api proxy.
export const localStatementEndpoint = "http://127.0.0.1:8000/workbench/dongwu-statement-check";

/** Keep private PDF bytes on a browser page served from this computer. */
export function canUploadLocalStatement(location: { protocol: string; hostname: string }): boolean {
  return (location.protocol === "http:" || location.protocol === "https:") &&
    ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname.toLowerCase());
}

const safeNotice = "仅核对所选账单内部一致性；非实时账户、非券商全量认证，不保存或授权交易。";
const countKeys = [
  "summary_row_count", "detail_row_count", "matched_group_count",
  "missing_summary_group_count", "extra_summary_group_count",
  "mismatched_group_count", "repaired_summary_rows", "footer_totals_mismatched_count",
] as const;
const safeKeys = new Set([
  "schema_version", "mode", "notice", "status", "period_start", "period_end",
  ...countKeys, "broker_reconciled", "full_account_verified",
  "trade_execution_enabled", "execution_ids_available", "execution_times_available",
  "footer_totals_checked",
]);

function validDay(value: unknown): value is string {
  if (typeof value !== "string" || !/^20\d{2}-\d{2}-\d{2}$/.test(value)) return false;
  const day = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === value;
}

export function parseDongwuStatementCheck(value: unknown): DongwuStatementCheck {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("对账单核对响应格式不符。");
  }
  const item = value as Record<string, unknown>;
  if (Object.keys(item).length !== safeKeys.size ||
      Object.keys(item).some((key) => !safeKeys.has(key)) ||
      item.schema_version !== "m8.dongwu_statement_check.v1" ||
      item.mode !== "local_pdf_preview" || item.notice !== safeNotice ||
      !validDay(item.period_start) || !validDay(item.period_end) ||
      item.period_start > item.period_end ||
      !countKeys.every((key) => Number.isSafeInteger(item[key]) && (item[key] as number) >= 0) ||
      item.broker_reconciled !== false || item.full_account_verified !== false ||
      item.trade_execution_enabled !== false || item.execution_ids_available !== false ||
      item.execution_times_available !== false || item.footer_totals_checked !== true) {
    throw new Error("对账单核对响应不可信。");
  }
  const discrepancies = (item.missing_summary_group_count as number) +
    (item.extra_summary_group_count as number) + (item.mismatched_group_count as number) +
    (item.footer_totals_mismatched_count as number);
  if ((item.status !== "matched_unverified" && item.status !== "mismatch") ||
      (item.status === "matched_unverified") !== (discrepancies === 0) ||
      (item.repaired_summary_rows as number) > (item.summary_row_count as number) ||
      (item.matched_group_count as number) + (item.mismatched_group_count as number) +
        (item.extra_summary_group_count as number) > (item.summary_row_count as number) ||
      (item.matched_group_count as number) + (item.mismatched_group_count as number) +
        (item.missing_summary_group_count as number) > (item.detail_row_count as number)) {
    throw new Error("对账单核对计数不一致。");
  }
  return item as DongwuStatementCheck;
}
