import { validObservedAt } from "./validObservedAt.ts";
import { DRAFT_KEY, readDrafts, type PlanDraft } from "./planDraftStore.ts";
import { REVIEW_KEY, readReviews } from "./reviewStore.ts";

/** Build a backup only after validating every stored draft version. */
export function serializeDraftBackup(
  storage: Pick<Storage, "getItem">,
  now: () => string = () => new Date().toISOString(),
): string {
  const records = readDrafts(storage);
  const exportedAt = now();
  if (!validObservedAt(exportedAt)) {
    throw new Error("备份时间无效，未生成导出文件。");
  }
  return JSON.stringify({
    schema_version: "m8.manual_drafts.v1",
    exported_at: exportedAt,
    records,
  }, null, 2);
}

/**
 * Restore an exported history only to a browser without existing draft data.
 * Validate the complete backup before the single storage write.
 */
export function restoreDraftBackup(
  storage: Pick<Storage, "getItem" | "setItem">,
  raw: string,
): PlanDraft[] {
  if (raw.length > 1_000_000) {
    throw new Error("备份文件超过1 MB，已拒绝导入。");
  }
  if (storage.getItem(DRAFT_KEY) !== null) {
    throw new Error("本浏览器已有草稿数据；为防止覆盖，禁止直接导入。");
  }
  let backup: unknown;
  try {
    backup = JSON.parse(raw);
  } catch {
    throw new Error("备份不是有效的 JSON 文件。");
  }
  if (backup === null || typeof backup !== "object" || Array.isArray(backup)) {
    throw new Error("备份格式不正确。");
  }
  const data = backup as Record<string, unknown>;
  if (data.schema_version !== "m8.manual_drafts.v1" ||
      typeof data.exported_at !== "string" ||
      !validObservedAt(data.exported_at) ||
      !Array.isArray(data.records) || data.records.length === 0) {
    throw new Error("备份版本、时间或记录不符合要求。");
  }
  const serialized = JSON.stringify(data.records);
  const records = readDrafts({
    getItem: (key: string) => key === DRAFT_KEY ? serialized : null,
  });
  const reviewSnapshot = storage.getItem(REVIEW_KEY);
  const reviews = readReviews(storage);
  const plans = new Map(records.map((item) => [item.id + ":" + item.version, item.symbol]));
  if (reviews.some((review) => plans.get(review.planId + ":" + review.version) !== review.symbol)) {
    throw new Error("复盘与待恢复的计划版本或证券不匹配，禁止导入。");
  }
  // Refuse an intervening write from another tab rather than silently overwriting it.
  if (storage.getItem(DRAFT_KEY) !== null) {
    throw new Error("导入期间出现新的本机草稿；已停止以避免覆盖。");
  }
  if (storage.getItem(REVIEW_KEY) !== reviewSnapshot) {
    throw new Error("导入期间复盘发生变化，请刷新后重试。");
  }
  storage.setItem(DRAFT_KEY, serialized);
  return records;
}
