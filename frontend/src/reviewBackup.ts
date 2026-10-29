import { validObservedAt } from "./validObservedAt.ts";
import { DRAFT_KEY, readDrafts } from "./planDraftStore.ts";
import { REVIEW_KEY, readReviews, type ManualReview } from "./reviewStore.ts";

type ReadableStore = Pick<Storage, "getItem">;
type WritableStore = Pick<Storage, "getItem" | "setItem">;
const MAX_BACKUP_SIZE = 1_000_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validExportTime(value: unknown): value is string {
  return validObservedAt(value);
}

/** Export only validated, browser-local manual reviews; no trade fills or P&L. */
export function serializeReviewBackup(
  storage: ReadableStore,
  now: () => string = () => new Date().toISOString(),
): string {
  const records = readReviews(storage);
  const exportedAt = now();
  if (!validExportTime(exportedAt)) {
    throw new Error("复盘备份时间无效，未生成导出文件。");
  }
  return JSON.stringify({
    schema_version: "m8.manual_reviews.v1",
    exported_at: exportedAt,
    source: "browser_local_manual",
    verified_fills: false,
    records,
  }, null, 2);
}

/**
 * Restore to an empty review store only. Every referenced plan version must
 * already exist locally, with the same symbol, to avoid orphaned history.
 */
export function restoreReviewBackup(
  storage: WritableStore,
  raw: string,
): ManualReview[] {
  if (raw.length > MAX_BACKUP_SIZE) {
    throw new Error("复盘备份超过1 MB，已拒绝导入。");
  }
  if (storage.getItem(REVIEW_KEY) !== null) {
    throw new Error("本浏览器已有复盘记录，禁止导入覆盖；请先备份现有记录。");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("复盘备份不是有效的 JSON 文件。");
  }
  if (!isRecord(parsed) ||
      parsed.schema_version !== "m8.manual_reviews.v1" ||
      !validExportTime(parsed.exported_at) ||
      parsed.source !== "browser_local_manual" ||
      parsed.verified_fills !== false ||
      !Array.isArray(parsed.records) || parsed.records.length === 0) {
    throw new Error("复盘备份版本、来源或记录不符合要求。");
  }

  // Validate every record with the same fail-closed rules as live storage.
  const serialized = JSON.stringify(parsed.records);
  const records = readReviews({
    getItem: (key: string) => key === REVIEW_KEY ? serialized : null,
  });
  const draftSnapshot = storage.getItem(DRAFT_KEY);
  const plans = readDrafts({ getItem: (key: string) => key === DRAFT_KEY ? draftSnapshot : null });
  const known = new Map(plans.map((plan) => [plan.id + ":" + plan.version, plan.symbol]));
  for (const review of records) {
    if (known.get(review.planId + ":" + review.version) !== review.symbol) {
      throw new Error("复盘引用的计划版本缺失或证券不匹配；请先恢复对应的计划草稿备份。");
    }
  }
  // Re-check before writing; another tab may have added reviews meanwhile.
  if (storage.getItem(REVIEW_KEY) !== null) {
    throw new Error("导入期间发现新的复盘记录，已停止以避免覆盖。");
  }
  if (storage.getItem(DRAFT_KEY) !== draftSnapshot) {
    throw new Error("导入期间计划发生变化，已停止恢复。");
  }
  storage.setItem(REVIEW_KEY, serialized);
  return records;
}
