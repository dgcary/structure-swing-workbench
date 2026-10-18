import { useState, type FormEvent } from "react";
import { readDrafts, saveDraft, type PlanDraft } from "./planDraftStore";
import { serializeDraftBackup } from "./planDraftBackup";
import { summarizeLocalDrafts, type LocalDraftSummary } from "./localDraftSummary";
const loadDrafts = () => readDrafts(localStorage);

export function LocalPlanDrafts({ history = false }: { history?: boolean }) {
  const [drafts, setDrafts] = useState<PlanDraft[]>(() => {
    try { return loadDrafts(); } catch { return []; }
  });
  const [error, setError] = useState(() => {
    try { loadDrafts(); return ""; } catch { return "本机草稿读取失败；为保护原数据已禁止保存。"; }
  });
  const [storageFault] = useState(() => { try { loadDrafts(); return false; } catch { return true; } });
  const [summary, setSummary] = useState<LocalDraftSummary | null>(() => {
    try { return summarizeLocalDrafts(localStorage); } catch { return null; }
  });
  const [symbol, setSymbol] = useState("");
  const [setup, setSetup] = useState("NONE");
  const [entry, setEntry] = useState("");
  const [stop, setStop] = useState("");
  const [target, setTarget] = useState("");
  const [notes, setNotes] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editingVersion, setEditingVersion] = useState<number | null>(null);

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (storageFault) return;
    try {
      const saved = saveDraft(localStorage,
        { symbol, setup, entry, stop, target, notes }, editing,
        undefined, undefined, editingVersion ?? undefined);
      setDrafts(saved.drafts);
      setSummary(summarizeLocalDrafts(localStorage));
      setEditing(saved.id);
      setEditingVersion(saved.drafts[0].version);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "本机草稿保存失败。");
    }
  }

  function exportBackup() {
    let url: string | null = null;
    try {
      const data = serializeDraftBackup(localStorage);
      url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "structure-swing-plan-drafts.json";
      link.click();
      const downloadUrl = url;
      window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      url = null;
      setError("");
    } catch (cause) {
      if (url !== null) {
        try { URL.revokeObjectURL(url); } catch { /* browser cleanup failed */ }
      }
      setError(cause instanceof Error ? "备份导出失败：" + cause.message :
        "备份导出失败，请检查本机存储与浏览器下载权限。");
    }
  }

  function edit(d: PlanDraft) {
    setEditing(d.id); setEditingVersion(d.version); setSymbol(d.symbol); setSetup(d.setup);
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
        value={symbol} disabled={editing !== null} onChange={(e) => setSymbol(e.target.value)} /></label>
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
        setEditing(null); setEditingVersion(null); setSymbol(""); setSetup("NONE"); setEntry("");
        setStop(""); setTarget(""); setNotes(""); setError("");
      }}>新建空白草稿</button>
    </form>}
    {history && <button className="back-button" type="button"
      disabled={drafts.length === 0 || storageFault} onClick={exportBackup}>
      导出本机历史备份（JSON）
    </button>}
    {summary && <p className="notice">本机共有 {summary.latest.length} 个独立人工计划、{summary.versionCount} 个草稿版本；均未审计，不代表有效计划。</p>}
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
