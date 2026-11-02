export type DailyClaimInput = {
  enabled: boolean;
  marketDate: string;
  exportedAt: string;
  completeThrough: string;
  exportReference: string;
  fillIds: string;
  declaredFullDay: boolean;
};

export type DailyFillClaim = {
  market_date: string;
  exported_at: string;
  complete_through: string;
  export_reference: string;
  expected_fill_ids: string[];
  declared_full_day: boolean;
};

export type DailyCoverage = {
  status: "matched_unverified" | "mismatch" | "insufficient";
  market_date: string;
  recorded_fill_count: number;
  declared_fill_count: number;
  missing_fill_count: number;
  unexpected_fill_count: number;
  missing_fill_ids: string[];
  unexpected_fill_ids: string[];
  detail_mismatch_fill_ids: string[] | null;
  duplicate_csv_rows: number;
  outside_watermark_fill_count: number;
  outside_claimed_day_fill_count: number;
  broker_reconciled: false;
  trade_execution_enabled: false;
  warning: string;
};

function validMarketDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function zonedInstant(value: string): number {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new Error("导出时间和覆盖水位须填写带时区的 ISO8601 时间。");
  }
  const instant = Date.parse(value);
  if (!Number.isFinite(instant)) throw new Error("导出时间或覆盖水位无效。");
  return instant;
}

export function buildDailyFillClaim(input: DailyClaimInput, hasFills: boolean): DailyFillClaim | null {
  if (!input.enabled) return null;
  if (!hasFills) throw new Error("逐日成交对照必须同时提供成交 CSV。");
  if (!validMarketDate(input.marketDate)) throw new Error("逐日成交对照的交易日无效。");
  const exported = zonedInstant(input.exportedAt);
  const through = zonedInstant(input.completeThrough);
  if (through > exported) throw new Error("成交覆盖水位不得晚于导出时间。");
  const reference = input.exportReference.trim();
  if (!reference || reference.length > 128) throw new Error("请填写有效的自报导出编号。");
  const ids = input.fillIds.split(/\r?\n/).map((id) => id.trim());
  if (!input.fillIds.trim()) throw new Error("请逐行填写自报成交编号。");
  if (ids.some((id) => !id)) throw new Error("成交编号清单不能包含空行。");
  if (ids.some((id) => id.length > 128) || ids.length > 10_000) {
    throw new Error("成交编号长度或数量超限。");
  }
  if (new Set(ids).size !== ids.length) throw new Error("自报成交编号重复。");
  return {
    market_date: input.marketDate,
    exported_at: input.exportedAt,
    complete_through: input.completeThrough,
    export_reference: reference,
    expected_fill_ids: ids,
    declared_full_day: input.declaredFullDay,
  };
}

export function parseDailyCoverage(value: unknown, expected: boolean): DailyCoverage | null {
  if (value === null && !expected) return null;
  if (!expected) throw new Error("未请求的逐日成交对照结果协议异常。");
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("逐日成交对照结果缺失或协议异常。");
  }
  const row = value as Record<string, unknown>;
  const status = row.status;
  const counts = [
    row.recorded_fill_count, row.declared_fill_count, row.missing_fill_count,
    row.unexpected_fill_count, row.duplicate_csv_rows,
    row.outside_watermark_fill_count, row.outside_claimed_day_fill_count,
  ];
  const mismatches = row.detail_mismatch_fill_ids;
  const missingIds = row.missing_fill_ids;
  const unexpectedIds = row.unexpected_fill_ids;
  const validIds = (ids: unknown): ids is string[] => Array.isArray(ids) &&
    ids.every((id) => typeof id === "string" && id.length > 0 && id.length <= 128) &&
    new Set(ids).size === ids.length;
  if (!(["matched_unverified", "mismatch", "insufficient"] as unknown[]).includes(status) ||
      !validMarketDate(String(row.market_date ?? "")) ||
      counts.some((count) => !Number.isSafeInteger(count) || (count as number) < 0) ||
      !validIds(missingIds) || !validIds(unexpectedIds) ||
      missingIds.length !== row.missing_fill_count ||
      unexpectedIds.length !== row.unexpected_fill_count ||
      !(mismatches === null || (Array.isArray(mismatches) &&
        mismatches.every((id) => typeof id === "string" && id.length > 0))) ||
      row.broker_reconciled !== false || row.trade_execution_enabled !== false ||
      typeof row.warning !== "string" || !row.warning.trim()) {
    throw new Error("逐日成交对照结果协议异常，不能作为券商认证。");
  }
  const hasMismatch = row.missing_fill_count !== 0 || row.unexpected_fill_count !== 0 ||
    row.duplicate_csv_rows !== 0 || row.outside_watermark_fill_count !== 0 ||
    (Array.isArray(mismatches) && mismatches.length > 0);
  if ((status === "mismatch") !== hasMismatch ||
      (status === "matched_unverified" && row.outside_claimed_day_fill_count !== 0)) {
    throw new Error("逐日成交对照状态与逐笔数量协议不一致。");
  }
  return row as DailyCoverage;
}
