import { useEffect, useRef, useState, type FormEvent } from "react";
import { assertTCyclePreview, type TCyclePreviewResult } from "./tCyclePreviewContract";

const emptyRisk = {
  account_equity: "", core_quantity: "", core_cost_price: "",
  main_invalidation_price: "", t_stop_price: "",
  existing_t_max_loss: "", other_positions_max_loss: "",
};

export function TCyclePreview() {
  const [symbol, setSymbol] = useState("");
  const [direction, setDirection] = useState("positive");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [closedQuantity, setClosedQuantity] = useState("");
  const [closedPrice, setClosedPrice] = useState("");
  const [risk, setRisk] = useState({ ...emptyRisk });
  const [result, setResult] = useState<TCyclePreviewResult | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const requestVersion = useRef(0);
  useEffect(() => () => { requestVersion.current++; }, []);

  function invalidate() { requestVersion.current++; setResult(null); setError(""); setPending(false); }
  function changeRisk(field: keyof typeof emptyRisk, value: string) {
    invalidate(); setRisk(previous => ({ ...previous, [field]: value }));
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); invalidate(); setPending(true);
    const version = requestVersion.current;
    try {
      const riskProvided = Object.values(risk).some(value => value.trim() !== "");
      if (riskProvided && Object.values(risk).some(value => value.trim() === "")) {
        throw new Error("反T风险估算需要完整填写七项手工假设；否则全部留空。");
      }
      const response = await fetch("/api/workbench/t-cycle-preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol, direction, open_quantity: quantity, open_price: price,
          close_quantity: closedQuantity || "0", close_price: closedPrice || null,
          risk_inputs: riskProvided ? risk : null,
        }),
      });
      const data = await response.json();
      if (version !== requestVersion.current) return;
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "输入无效");
      assertTCyclePreview(data, {
        symbol, direction: direction as "positive" | "reverse", expectRisk: riskProvided,
      });
      setResult(data);
    } catch (cause) {
      if (version === requestVersion.current) setError(cause instanceof Error ? cause.message : "预览失败");
    } finally { if (version === requestVersion.current) setPending(false); }
  }
  return <section className="panel">
    <h2>T仓 · 单次手工计算</h2>
    <p className="notice">仅数学预览，不保存、不对账、不校验T+1及当日次数，也不授权交易。</p>
    <form className="plan-form" onSubmit={submit}>
      <label>证券代码<input required pattern="[0-9]{6}" value={symbol} onChange={e => { invalidate(); setSymbol(e.target.value); }} /></label>
      <label>方向<select value={direction} onChange={e => { invalidate(); setDirection(e.target.value); setRisk({ ...emptyRisk }); }}>
        <option value="positive">正T：先卖后买回</option><option value="reverse">反T：先买后卖旧仓</option>
      </select></label>
      <label>首笔数量<input required type="number" min="0.00000001" step="any" value={quantity} onChange={e => { invalidate(); setQuantity(e.target.value); }} /></label>
      <label>首笔价格<input required type="number" min="0.00000001" step="any" value={price} onChange={e => { invalidate(); setPrice(e.target.value); }} /></label>
      <label>闭环数量（可留空）<input type="number" min="0" step="any" value={closedQuantity} onChange={e => { invalidate(); setClosedQuantity(e.target.value); }} /></label>
      <label>闭环价格（可留空）<input type="number" min="0.00000001" step="any" value={closedPrice} onChange={e => { invalidate(); setClosedPrice(e.target.value); }} /></label>
      {direction === "reverse" && <details>
        <summary>反T最大暴露与独立止损估算（可选，全部为手工假设）</summary>
        <p className="notice">必须同时填写全部七项。既有T仓和其他持仓的最大亏损需自行完整汇总；结果无法证明账户、T+1可卖数量或交易许可。</p>
        <label>账户总权益（元）<input type="number" min="0.00000001" step="any" value={risk.account_equity} onChange={e => changeRisk("account_equity", e.target.value)} /></label>
        <label>核心仓数量<input type="number" min="0" step="any" value={risk.core_quantity} onChange={e => changeRisk("core_quantity", e.target.value)} /></label>
        <label>核心仓策略成本价<input type="number" min="0.00000001" step="any" value={risk.core_cost_price} onChange={e => changeRisk("core_cost_price", e.target.value)} /></label>
        <label>主计划结构失效价<input type="number" min="0.00000001" step="any" value={risk.main_invalidation_price} onChange={e => changeRisk("main_invalidation_price", e.target.value)} /></label>
        <label>本次反T独立止损价<input type="number" min="0.00000001" step="any" value={risk.t_stop_price} onChange={e => changeRisk("t_stop_price", e.target.value)} /></label>
        <label>既有T仓最大亏损合计（元；无则填0）<input type="number" min="0" step="any" value={risk.existing_t_max_loss} onChange={e => changeRisk("existing_t_max_loss", e.target.value)} /></label>
        <label>其他持仓最大亏损合计（元；无则填0）<input type="number" min="0" step="any" value={risk.other_positions_max_loss} onChange={e => changeRisk("other_positions_max_loss", e.target.value)} /></label>
      </details>}
      <button type="submit" disabled={pending}>{pending ? "计算中…" : "计算本次循环"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <div className="plan-result" role="status">
      <strong>{result.cycle_status === "closed" ? "本次输入已闭环" : "本次输入未闭环"}</strong>
      <p>剩余未配对数量：{result.remaining_quantity}</p>
      <p>{result.realized_gross_pnl !== null
        ? "完整循环毛盈亏：" + result.realized_gross_pnl
        : "已配对部分毛盈亏（未闭环）：" + (result.pending_matched_gross_pnl ?? "未知")} 元</p>
      {result.projected_risk && <div>
        <strong>反T买入后的手工最大暴露估算（非正式审计）</strong>
        <p>核心仓最大亏损：{result.projected_risk.core_max_loss} 元；本次T仓最大亏损：{result.projected_risk.new_t_max_loss} 元</p>
        <p>本票（含既有T仓）最大亏损：{result.projected_risk.projected_max_loss} 元；占输入权益：{result.projected_risk.projected_account_risk_pct}%</p>
        <p>本次交易动作风险等级（仅数学分级）：{result.projected_risk.level === "PASS" ? "常规范围（≤2%）" :
          result.projected_risk.level === "WARNING" ? "风险提醒（>2%～3%）" : "本票超过硬性上限（>3%）"}</p>
        <p>其他股票最大亏损：{result.projected_risk.other_positions_max_loss} 元；账户风险合计（仅展示）：{result.projected_risk.account_total_max_loss} 元，占输入权益 {result.projected_risk.account_total_risk_pct}%（不参与本票风险分级）</p>
        <p>{result.projected_risk.warning}</p>
      </div>}
      <p>{result.notice}</p>
    </div>}
  </section>;
}
