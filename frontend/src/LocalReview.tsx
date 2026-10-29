import { useState, type FormEvent } from "react";
import { readDrafts, type PlanDraft } from "./planDraftStore";
import { REVIEW_KEY, readReviews, saveReview, type ManualReview } from "./reviewStore";
import { restoreReviewBackup, serializeReviewBackup } from "./reviewBackup";

const loadPlans = () => readDrafts(localStorage);
const loadReviews = () => readReviews(localStorage);

export function LocalReview() {
  const [planList, setPlanList] = useState<PlanDraft[]>(() => {
    try { return loadPlans(); } catch { return []; }
  });
  const [items, setItems] = useState<ManualReview[]>(() => {
    try { return loadReviews(); } catch { return []; }
  });
  const [fault, setFault] = useState(() => {
    try { loadPlans(); loadReviews(); return ""; }
    catch { return "本机计划或复盘记录损坏，已禁止写入以保护原数据。"; }
  });
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [observation, setObservation] = useState("");
  const [lesson, setLesson] = useState("");
  const [importError, setImportError] = useState("");

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (fault) return;
    let currentPlans: PlanDraft[];
    try {
      currentPlans = loadPlans();
      loadReviews();
    } catch {
      setFault("本机记录读取失败，已禁止写入以保护原数据。");
      return;
    }
    const plan = currentPlans.find((p) => p.id + ":" + p.version === selected);
    if (!plan) {
      setError("关联计划版本已变化，请刷新后重新选择。");
      return;
    }
    try {
      const next = saveReview(localStorage, plan, observation, lesson);
      setItems(next);
      setPlanList(currentPlans);
      setObservation("");
      setLesson("");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存复盘失败，原记录未修改。");
      try { loadReviews(); }
      catch { setFault("复盘数据异常，已禁止写入以保护原数据。"); }
    }
  }

  function refresh() {
    try {
      setPlanList(loadPlans());
      setItems(loadReviews());
      setFault("");
      setError("");
      setSelected("");
    } catch {
      setFault("本机记录损坏或无法读取，已禁止写入。");
    }
  }

  function exportBackup() {
    let url: string | null = null;
    try {
      const data = serializeReviewBackup(localStorage);
      url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "structure-swing-reviews.json";
      link.click();
      const downloadUrl = url;
      window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      url = null;
      setError("");
    } catch (cause) {
      if (url !== null) {
        try { URL.revokeObjectURL(url); } catch { /* cleanup best effort */ }
      }
      setError(cause instanceof Error ? "复盘导出失败：" + cause.message :
        "复盘导出失败，请检查本机存储和下载权限。");
    }
  }

  async function importBackup(file?: File) {
    if (!file) return;
    if (file.size > 1_000_000) {
      setImportError("复盘备份超过1 MB，已拒绝导入。");
      return;
    }
    try {
      const restored = restoreReviewBackup(localStorage, await file.text());
      setItems(restored);
      setPlanList(loadPlans());
      setFault("");
      setImportError("");
      setError("");
    } catch (cause) {
      setImportError(cause instanceof Error ? cause.message : "复盘备份导入失败。");
    }
  }

  let canRestore = false;
  try { canRestore = localStorage.getItem(REVIEW_KEY) === null; }
  catch { canRestore = false; }

  return <section className="panel">
    <h2>人工计划复盘（本机保存）</h2>
    <p className="notice">仅记录人工观察并关联计划版本；未核验成交、不计算收益、
      不生成买卖信号或正式审计记录。清除浏览器数据会丢失记录。</p>
    {fault && <p role="alert">{fault}</p>}
    {error && <p role="alert">{error}</p>}
    {importError && <p role="alert">导入失败：{importError}</p>}
    <button type="button" className="back-button" onClick={refresh}>刷新本机计划</button>
    {planList.length === 0 ? <p>请先在计划管理保存人工草稿。</p> :
      <form className="csv-preview-form" onSubmit={save}>
        <label>关联计划版本<select required value={selected}
          onChange={(e) => setSelected(e.target.value)}>
          <option value="">请选择计划</option>
          {planList.map((p) => <option key={p.id + ":" + p.version}
            value={p.id + ":" + p.version}>{p.symbol} · 第{p.version}版</option>)}
        </select></label>
        <label>人工观察<textarea required maxLength={2000} value={observation}
          onChange={(e) => setObservation(e.target.value)} /></label>
        <label>复盘结论<textarea required maxLength={2000} value={lesson}
          onChange={(e) => setLesson(e.target.value)} /></label>
        <button disabled={Boolean(fault)} type="submit">保存新复盘（不覆盖历史）</button>
      </form>}
    <button type="button" className="back-button" disabled={!items.length || Boolean(fault)}
      onClick={exportBackup}>导出复盘 JSON 备份</button>
    <div className="csv-preview-form">
      <p className="notice">恢复复盘前请先恢复对应的计划草稿。仅允许导入到没有复盘记录的浏览器；
        不合并、不覆盖、不上传服务器，恢复后仍属未经核验的人工记录。</p>
      <label>恢复本机复盘备份（JSON）
        <input type="file" accept=".json,application/json"
          disabled={!canRestore || Boolean(fault)}
          onChange={(event) => {
            void importBackup(event.target.files?.[0]);
            event.target.value = "";
          }} />
      </label>
    </div>
    {items.map((r) => <article key={r.id} className="draft-card">
      <strong>{r.symbol} · 计划第{r.version}版 · 未核验成交</strong>
      <p>时间：{new Date(r.savedAt).toLocaleString("zh-CN")}</p>
      <p>人工观察：{r.observation}</p><p>复盘结论：{r.lesson}</p>
    </article>)}
  </section>;
}
