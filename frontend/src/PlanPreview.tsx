import { useState, type FormEvent } from "react";

const labels = {
  symbol: "证券代码", account_equity: "账户权益", planned_quantity: "计划数量",
  planned_entry_price: "入场价格", invalidation_price: "结构失效价",
  initial_pct: "位置试仓%", confirmation_pct: "确认加仓%", t_reserve_pct: "机动仓%",
} as const;
type Key = keyof typeof labels;
const defaults: Record<Key, string> = {
  symbol: "", account_equity: "", planned_quantity: "",
  planned_entry_price: "", invalidation_price: "",
  initial_pct: "40", confirmation_pct: "30", t_reserve_pct: "30",
};
type Result = { schema_version: string; executable: boolean; formal_audit_completed: boolean;
  trade_execution_enabled: boolean; highest_checked_level_zh: string;
  account_risk_pct: string; notice: string; findings: { level: string; level_zh: string; message: string }[] };

export function PlanPreview() {
  const [values, setValues] = useState(defaults);
  const [action, setAction] = useState("");
  const [invalidated, setInvalidated] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null); setError("");
    try {
      const response = await fetch("/api/workbench/plan-preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...values, action_type: action, structure_invalidated: invalidated === "yes" }),
      });
      if (!response.ok) throw new Error("输入校验或预审接口失败");
      const data = await response.json() as Result;
      if (data.schema_version !== "m8.plan_preview.v1" || data.executable ||
          data.formal_audit_completed || data.trade_execution_enabled) throw new Error("预审协议异常");
      setResult(data);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "请求失败"); }
  }
  return <section className="panel"><h2>人工计划 · 局部纪律预审</h2>
    <p className="notice">不保存、不完成正式审计、不授权交易；结构判断由用户提供。</p>
    <form className="plan-form" onSubmit={submit}>
      {(Object.keys(labels) as Key[]).map((key) => <label key={key}>{labels[key]}
        <input required type={key === "symbol" ? "text" : "number"} step="any"
          pattern={key === "symbol" ? "[0-9]{6}" : undefined} value={values[key]}
          onChange={(e) => { setValues((old) => ({ ...old, [key]: e.target.value })); setResult(null); }} />
      </label>)}
      <label>用户计划动作<select required value={action} onChange={(e) => { setAction(e.target.value); setResult(null); }}>
        <option value="">请选择</option><option value="initial_entry">初始建仓</option>
        <option value="confirmation_add">确认加仓</option><option value="reverse_t_buy">反T先买</option>
        <option value="positive_t_sell">正T先卖</option><option value="take_profit">止盈</option>
        <option value="stop_exit">止损退出</option>
      </select></label>
      <label>结构是否失效<select required value={invalidated} onChange={(e) => { setInvalidated(e.target.value); setResult(null); }}>
        <option value="">请明确选择</option><option value="yes">是</option><option value="no">否</option>
      </select></label>
      <button type="submit">预审已填写字段</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <section className="plan-result"><strong>局部预审：{result.highest_checked_level_zh} · 不可执行</strong>
      <p>账户风险：{result.account_risk_pct}%</p><p>{result.notice}</p>
      <ul>{result.findings.filter((f) => f.level !== "pass").map((f, i) =>
        <li key={i}>{f.level_zh}：{f.message}</li>)}</ul>
      <details><summary>展开通过项</summary><ul>{result.findings.filter((f) => f.level === "pass").map((f, i) =>
        <li key={i}>{f.message}</li>)}</ul></details>
    </section>}
  </section>;
}
