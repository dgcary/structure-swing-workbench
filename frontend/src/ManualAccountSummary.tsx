import { useEffect, useState } from "react";
import { canUseManualJournal, parseManualJournal, type ManualJournalRecord } from "./manualJournalContract";
import { summarizeManualAccount } from "./manualOverview";

export function ManualAccountSummary({ onOpen }: { onOpen: () => void }) {
  const [record, setRecord] = useState<ManualJournalRecord | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  async function load() {
    if (!canUseManualJournal(window.location)) {
      setState("error"); setError("请通过可信 HTTPS 打开家庭工作台。"); return;
    }
    setState("loading"); setError("");
    try {
      const response = await fetch("/api/workbench/manual-journal");
      if (!response.ok) throw new Error(response.status === 404
        ? "手工台账尚未启用。" : "手工台账暂时无法读取，请刷新或重新登录。");
      const payload: unknown = await response.json();
      setRecord(parseManualJournal(payload).latest);
      setState("ready");
    } catch (cause) {
      setState("error");
      setError(cause instanceof Error ? cause.message : "手工台账暂时无法读取。");
    }
  }

  useEffect(() => { void load(); }, []);
  const summary = record ? summarizeManualAccount(record) : null;

  return <section className="panel" aria-label="手工账户摘要">
    <h2>我的手工账户 · 自行记录</h2>
    <p className="notice">来自你保存的台账，未经券商自动核对。金额和数量以最近一次核对为准；不计算实时市值、仓位比例或交易风险。</p>
    {state === "loading" && <p role="status">正在读取手工台账…</p>}
    {state === "error" && <p role="alert">{error}</p>}
    {state === "ready" && !summary && <p>尚未登记当前仓位。</p>}
    {state === "ready" && summary && <>
      <p>最近核对：{new Date(summary.observedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</p>
      <div className="metric-grid" aria-label="手工记录的账户信息">
        <article className="metric-card"><h3>可用资金 · 手工记录</h3><div className="metric-value">{summary.availableCash ?? "未填写"}{summary.availableCash && <small>元</small>}</div></article>
        <article className="metric-card"><h3>账户总权益 · 手工记录</h3><div className="metric-value">{summary.totalEquity ?? "未填写"}{summary.totalEquity && <small>元</small>}</div></article>
        <article className="metric-card"><h3>持仓股票数 · 手工记录</h3><div className="metric-value">{summary.stockCount}<small>只</small></div></article>
      </div>
      <div className="holding-list">
        {summary.lots.map((lot, index) => <article className="holding-card" key={`${lot.symbol}-${index}`}>
          <h3>{lot.symbol} · {lot.quantity} 股</h3>
          <p>买入时间：{lot.bought_at ? new Date(lot.bought_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) : "未填写"} · 登记投入：{lot.paid_amount ? `${lot.paid_amount} 元` : "未填写"}</p>
        </article>)}
      </div>
    </>}
    <button className="back-button" type="button" onClick={onOpen}>查看或修改手工台账</button>
    <button className="back-button" type="button" onClick={() => { void load(); }}>刷新手工记录</button>
  </section>;
}
