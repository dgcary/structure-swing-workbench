import { readDrafts } from "./planDraftStore.ts";

/** Build a backup only after validating every stored draft version. */
export function serializeDraftBackup(
  storage: Pick<Storage, "getItem">,
  now: () => string = () => new Date().toISOString(),
): string {
  const records = readDrafts(storage);
  const exportedAt = now();
  if (!Number.isFinite(Date.parse(exportedAt))) {
    throw new Error("备份时间无效，未生成导出文件。");
  }
  return JSON.stringify({
    schema_version: "m8.manual_drafts.v1",
    exported_at: exportedAt,
    records,
  }, null, 2);
}
