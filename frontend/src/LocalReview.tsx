import { useState, type FormEvent } from "react";

type Draft = { id: string; version: number; symbol: string; savedAt: string };
type Review = { id: string; planId: string; version: number; symbol: string;
  savedAt: string; observation: string; lesson: string };
const PLAN_KEY = "structure-swing.m8.manual-drafts.v1";
const REVIEW_KEY = "structure-swing.m8.manual-reviews.v1";

function readArray(key: string): unknown[] {
  const raw = localStorage.getItem(key);
  const data: unknown = raw ? JSON.parse(raw) : [];
  if (!Array.isArray(data) || data.length > 200) throw new Error("本机数据格式错误");
  return data;
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
function plans(): Draft[] {
  const data = readArray(PLAN_KEY);
  if (!data.every((v) => isRecord(v) && typeof v.id === "string" &&
    typeof v.version === "number" && Number.isSafeInteger(v.version) && v.version > 0 &&
    typeof v.symbol === "string" && /^[0-9]{6}$/.test(v.symbol) &&
    typeof v.savedAt === "string"))
    throw new Error("计划版本数据损坏");
  return data as Draft[];
}
function reviews(): Review[] {
  const data = readArray(REVIEW_KEY);
  if (!data.every((v) => isRecord(v) && typeof v.id === "string" &&
    typeof v.planId === "string" && typeof v.version === "number" &&
    Number.isSafeInteger(v.version) && v.version > 0 &&
    typeof v.symbol === "string" && /^[0-9]{6}$/.test(v.symbol) &&
    typeof v.savedAt === "string" && typeof v.observation === "string" &&
    v.observation.length <= 2000 && typeof v.lesson === "string" &&
    v.lesson.length <= 2000))
    throw new Error("复盘数据损坏");
  return data as Review[];
}

export function LocalReview() {
  const [planList, setPlanList] = useState<Draft[]>(() => {
    try { return plans(); } catch { return []; }
  });
  const [items, setItems] = useState<Review[]>(() => {
    try { return reviews(); } catch { return []; }
  });
  const [fault, setFault] = useState(() => {
    try { plans(); reviews(); return ""; } catch { return "本机记录损坏，已禁止写入。"; }
  });
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [observation, setObservation] = useState("");
  const [lesson, setLesson] = useState("");

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (fault) return;
    try {
      const currentPlans = plans(), currentReviews = reviews();
      const plan = currentPlans.find((p) => p.id + ":" + p.version === selected);
      if (!plan || !observation.trim() || !lesson.trim() ||
        observation.length > 2000 || lesson.length > 2000 ||
        currentReviews.length >= 200) {
        setError("请选择有效计划版本并填写不超过2000字的复盘内容（最多200条）。");
        return;
      }
      const record: Review = {
        id: crypto.randomUUID(), planId: plan.id, version: plan.version,
        symbol: plan.symbol, savedAt: new Date().toISOString(),
        observation: observation.trim(), lesson: lesson.trim(),
      };
      const next = [record, ...currentReviews];
      localStorage.setItem(REVIEW_KEY, JSON.stringify(next));
      setItems(next); setObservation(""); setLesson(""); setError("");
    } catch { setFault("读取或保存失败，已停止写入以保护原数据。"); }
  }
  function refresh() {
    try { setPlanList(plans()); setItems(reviews()); setError(""); }
    catch { setFault("本机数据损坏，已停止写入。"); }
  }
  function exportBackup() {
    try {
      const data = JSON.stringify({ schema_version: "m8.manual_reviews.v1",
        source: "browser_local_manual", verified_fills: false, records: reviews() }, null, 2);
      const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "structure-swing-reviews.json"; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("导出失败：本机复盘数据无法读取。"); }
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
