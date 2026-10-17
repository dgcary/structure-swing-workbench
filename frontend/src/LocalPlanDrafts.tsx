import { useState, type FormEvent } from "react";

type Draft = {
  id: string; version: number; savedAt: string; symbol: string;
  setup: string; entry: string; stop: string; target: string; notes: string;
};
const KEY = "structure-swing.m8.manual-drafts.v1";

function readDrafts(): Draft[] {
  const raw = localStorage.getItem(KEY);
  if (!raw) return [];
  const value: unknown = JSON.parse(raw);
  if (!Array.isArray(value) || value.length > 200 || !value.every((item) =>
    item && typeof item.id === "string" && Number.isSafeInteger(item.version) &&
    item.version > 0 && typeof item.savedAt === "string" &&
    /^[0-9]{6}$/.test(item.symbol) &&
    ["C", "A", "B", "NONE"].includes(item.setup) &&
    ["entry", "stop", "target", "notes"].every((key) => typeof item[key] === "string")
  )) throw new Error("本机草稿记录损坏；已停止写入，避免覆盖原数据。");
  return value as Draft[];
}

export function LocalPlanDrafts({ history = false }: { history?: boolean }) {
  const [drafts, setDrafts] = useState<Draft[]>(() => {
    try { return readDrafts(); } catch { return []; }
  });
  const [error, setError] = useState(() => {
    try { readDrafts(); return ""; } catch { return "本机草稿读取失败；为保护原数据已禁止保存。"; }
  });
  const [storageFault] = useState(() => { try { readDrafts(); return false; } catch { return true; } });
  const [symbol, setSymbol] = useState("");
  const [setup, setSetup] = useState("NONE");
  const [entry, setEntry] = useState("");
  const [stop, setStop] = useState("");
  const [target, setTarget] = useState("");
  const [notes, setNotes] = useState("");
  const [editing, setEditing] = useState<string | null>(null);

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (storageFault) return;
    if (!/^[0-9]{6}$/.test(symbol) || ![entry, target].every((v) =>
      v.trim() && Number.isFinite(Number(v)) && Number(v) > 0) ||
      !Number.isFinite(Number(stop)) || stop.trim() === "" ||
      Number(stop) < 0 || Number(stop) >= Number(entry)) {
      setError("请核对证券代码、价格和结构失效价。");
      return;
    }
    if (drafts.length >= 200) { setError("已达200个版本上限，请先备份。"); return; }
    const id = editing ?? (Date.now().toString(36) + Math.random().toString(36).slice(2));
    const version = drafts.filter((d) => d.id === id).reduce((v, d) =>
      Math.max(v, d.version), 0) + 1;
    const next = [{ id, version, savedAt: new Date().toISOString(),
      symbol, setup, entry, stop, target, notes }, ...drafts];
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
      setDrafts(next);
      setEditing(id);
      setError("");
    } catch { setError("浏览器本机存储失败，草稿未保存。"); }
  }

  function exportBackup() {
    const data = JSON.stringify({
      schema_version: "m8.manual_drafts.v1", exported_at: new Date().toISOString(),
      records: drafts,
    }, null, 2);
    const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "structure-swing-plan-drafts.json";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function edit(d: Draft) {
    setEditing(d.id); setSymbol(d.symbol); setSetup(d.setup);
    setEntry(d.entry); setStop(d.stop); setTarget(d.target); setNotes(d.notes);
    setError("");
  }

  return <section className="panel">
    <h2>{history ? "历史计划草稿" : "人工计划草稿（本机保存）"}</h2>
    <p className="notice">仅保存在此浏览器，未同步服务器或券商；不是有效交易计划，
      未完成正式纪律审计，不能据此执行交易。清除浏览器数据会丢失记录。</p>
    {error && <p role="alert">{error}</p>}
    {!history && <form className="plan-form" onSubmit={save}>
      <label>证券代码<input required pattern="[0-9]{6}" maxLength={6}
        value={symbol} onChange={(e) => setSymbol(e.target.value)} /></label>
      <label>人工指定 Setup<select value={setup} onChange={(e) => setSetup(e.target.value)}>
        <option value="NONE">未判断</option><option value="C">C 类</option>
        <option value="A">A 类</option><option value="B">B 类</option>
      </select></label>
      <label>计划入场价<input required type="number" min="0" step="any"
        value={entry} onChange={(e) => setEntry(e.target.value)} /></label>
      <label>结构失效价<input required type="number" min="0" step="any"
        value={stop} onChange={(e) => setStop(e.target.value)} /></label>
      <label>第一目标价<input required type="number" min="0" step="any"
        value={target} onChange={(e) => setTarget(e.target.value)} /></label>
      <label>人工备注<input maxLength={2000}
        value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      <button type="submit" disabled={storageFault}>{editing ? "保存新版本" : "保存本机草稿"}</button>
      <button type="button" onClick={() => {
        setEditing(null); setSymbol(""); setSetup("NONE"); setEntry("");
        setStop(""); setTarget(""); setNotes(""); setError("");
      }}>新建空白草稿</button>
    </form>}
    {history && <button className="back-button" type="button"
      disabled={drafts.length === 0 || storageFault} onClick={exportBackup}>
      导出本机历史备份（JSON）
    </button>}
    {drafts.length === 0 && <p>尚无本机计划草稿。</p>}
    {drafts.map((d) => <article key={d.id + ":" + d.version} className="draft-card">
      <strong>{d.symbol} · 第{d.version}版 · 未审计</strong>
      <p>Setup：{d.setup === "NONE" ? "未判断" : d.setup} ·
        入场：{d.entry} · 失效：{d.stop} · 第一目标：{d.target}</p>
      <p>保存时间：{new Date(d.savedAt).toLocaleString("zh-CN")} · 来源：本浏览器人工输入</p>
      {d.notes && <p>人工备注：{d.notes}</p>}
      {!history && !drafts.some((other) => other.id === d.id && other.version > d.version) &&
        <button type="button" onClick={() => edit(d)}>修订并保留旧版</button>}
    </article>)}
  </section>;
}
