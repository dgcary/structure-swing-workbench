import { useState, type FormEvent } from "react";
import { readDrafts, type PlanDraft } from "./planDraftStore";
import { readReviews, saveReview, type ManualReview } from "./reviewStore";

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
    try {
      const data = JSON.stringify({
        schema_version: "m8.manual_reviews.v1",
        source: "browser_local_manual",
        verified_fills: false,
        records: loadReviews(),
      }, null, 2);
      const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "structure-swing-reviews.json";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError("导出失败：本机复盘数据无法读取。");
    }
  }

  return <section className="panel">
    <h2>人工计划复盘（本机保存）</h2>
    <p className="notice">仅记录人工观察并关联计划版本；未核验成交、不计算收益、
      不生成买卖信号或正式审计记录。清除浏览器数据会丢失记录。</p>
    {fault && <p role="alert">{fault}</p>}
    {error && <p role="alert">{error}</p>}
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
    <button type="button" className="back-button" disabled={!items.length}
      onClick={exportBackup}>导出复盘 JSON 备份</button>
    {items.map((r) => <article key={r.id} className="draft-card">
      <strong>{r.symbol} · 计划第{r.version}版 · 未核验成交</strong>
      <p>时间：{new Date(r.savedAt).toLocaleString("zh-CN")}</p>
      <p>人工观察：{r.observation}</p><p>复盘结论：{r.lesson}</p>
    </article>)}
  </section>;
}
