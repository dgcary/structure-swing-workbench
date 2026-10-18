import { useState } from "react";
import { restoreDraftBackup } from "./planDraftBackup";
import type { PlanDraft } from "./planDraftStore";

export function LocalDraftImport({
  disabled, onImported,
}: {
  disabled: boolean; onImported: (records: PlanDraft[]) => void;
}) {
  const [error, setError] = useState("");
  async function importFile(file?: File) {
    if (!file || disabled) return;
    if (file.size > 1_000_000) {
      setError("备份文件超过1 MB，已拒绝导入。");
      return;
    }
    try {
      const records = restoreDraftBackup(localStorage, await file.text());
      onImported(records);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "备份导入失败");
    }
  }
  return <div className="csv-preview-form">
    <p className="notice">仅可向没有草稿的浏览器恢复备份；不覆盖现有记录，不上传服务器，导入后仍未正式审计。</p>
    <label>恢复本机历史备份（JSON）
      <input type="file" accept=".json,application/json" disabled={disabled}
        onChange={(event) => {
          void importFile(event.target.files?.[0]);
          event.target.value = "";
        }} />
    </label>
    {error && <p role="alert">导入失败：{error}</p>}
  </div>;
}
