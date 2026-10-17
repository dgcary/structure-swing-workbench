import { useEffect, useRef, useState, type FormEvent } from "react";

type TPreview = {
  schema_version: string;
  cycle_status: "open" | "closed";
  remaining_quantity: string;
  realized_gross_pnl: string | null;
  pending_matched_gross_pnl: string | null;
  notice: string;
  persisted: boolean;
  broker_reconciled: boolean;
  daily_cycle_limit_verified: boolean;
  trade_execution_enabled: boolean;
};

export function TCyclePreview() {
  const [symbol, setSymbol] = useState("");
  const [direction, setDirection] = useState("positive");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [closedQuantity, setClosedQuantity] = useState("");
  const [closedPrice, setClosedPrice] = useState("");
  const [result, setResult] = useState<TPreview | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const requestVersion = useRef(0);
  useEffect(() => () => { requestVersion.current++; }, []);

  function invalidate() { requestVersion.current++; setResult(null); setError(""); setPending(false); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); invalidate(); setPending(true);
    const version = requestVersion.current;
    try {
      const response = await fetch("/api/workbench/t-cycle-preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol, direction, open_quantity: quantity, open_price: price,
          close_quantity: closedQuantity || "0", close_price: closedPrice || null,
        }),
      });
      const data = await response.json();
      if (version !== requestVersion.current) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "输入无效");
      const preview = data as TPreview;
      if (preview.schema_version !== "m8.t_cycle_preview.v1" ||
          preview.persisted !== false || preview.broker_reconciled !== false ||
          preview.daily_cycle_limit_verified !== false ||
          preview.trade_execution_enabled !== false) throw new Error("预览协议异常");
      setResult(preview);
    } catch (cause) {
      if (version === requestVersion.current) setError(cause instanceof Error ? cause.message : "预览失败");
    } finally { if (version === requestVersion.current) setPending(false); }
  }
  return <section className="panel">
    <h2>T仓 · 单次手工计算</h2>
    <p className="notice">仅数学预览，不保存、不对账、不校验T+1及当日次数，也不授权交易。</p>
    <form className="plan-form" onSubmit={submit}>
      <label>证券代码<input required pattern="[0-9]{6}" value={symbol} onChange={e => { invalidate(); setSymbol(e.target.value); }} /></label>
      <label>方向<select value={direction} onChange={e => { invalidate(); setDirection(e.target.value); }}>
        <option value="positive">正T：先卖后买回</option><option value="reverse">反T：先买后卖旧仓</option>
      </select></label>
      <label>首笔数量<input required type="number" min="0.00000001" step="any" value={quantity} onChange={e => { invalidate(); setQuantity(e.target.value); }} /></label>
      <label>首笔价格<input required type="number" min="0.00000001" step="any" value={price} onChange={e => { invalidate(); setPrice(e.target.value); }} /></label>
      <label>闭环数量（可留空）<input type="number" min="0" step="any" value={closedQuantity} onChange={e => { invalidate(); setClosedQuantity(e.target.value); }} /></label>
      <label>闭环价格（可留空）<input type="number" min="0.00000001" step="any" value={closedPrice} onChange={e => { invalidate(); setClosedPrice(e.target.value); }} /></label>
      <button type="submit" disabled={pending}>{pending ? "计算中…" : "计算本次循环"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <div className="plan-result" role="status">
      <strong>{result.cycle_status === "closed" ? "本次输入已闭环" : "本次输入未闭环"}</strong>
      <p>剩余未配对数量：{result.remaining_quantity}</p>
      <p>{result.realized_gross_pnl !== null
        ? "完整循环毛盈亏：" + result.realized_gross_pnl
        : "已配对部分毛盈亏（未闭环）：" + (result.pending_matched_gross_pnl ?? "未知")} 元</p>
      <p>{result.notice}</p>
    </div>}
  </section>;
}
