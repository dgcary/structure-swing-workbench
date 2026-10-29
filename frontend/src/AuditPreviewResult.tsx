/** A partial, user-supplied plan check is never a formal execution approval. */
export type PartialAuditResult = {
  schema_version: "m8.plan_preview.v1";
  mode: "partial_preview";
  symbol: string;
  input_source: "user";
  persisted: false;
  formal_audit_completed: false;
  executable: false;
  trade_execution_enabled: false;
  highest_checked_level: string;
  highest_checked_level_zh: string;
  account_risk_pct: string;
  notice: string;
  findings: { rule: string; level: string; level_zh: string; message: string }[];
};

const priority: Record<string, number> = {
  hard_fail: 0, overridable_fail: 1, warning: 2, pass: 3,
};

export function AuditPreviewResult({ result }: { result: PartialAuditResult }) {
  const findings = [...result.findings].sort(
    (a, b) => (priority[a.level] ?? 4) - (priority[b.level] ?? 4),
  );
  const exceptions = findings.filter((finding) => finding.level !== "pass");
  const passes = findings.filter((finding) => finding.level === "pass");
  return <section className="plan-result" aria-label="局部纪律预审结果">
    <strong>局部预审：{result.highest_checked_level_zh} · 不可认定可执行</strong>
    <p>证券代码：{result.symbol} · 按已填字段计算的账户风险：{result.account_risk_pct}%</p>
    <p className="notice">{result.notice}</p>
    <p>仅核验本次手工输入，不代表完整交易计划审计；结果不保存、不授权交易。</p>
    {exceptions.length > 0
      ? <ul aria-label="不通过及待核查项">{exceptions.map((finding, index) =>
        <li key={`${finding.rule}-${index}`}><strong>{finding.level_zh}</strong>：{finding.message}</li>,
      )}</ul>
      : <p>已检查字段未发现异常，但其余必要审计尚未完成。</p>}
    <details><summary>已检查的通过项（{passes.length}）</summary>
      <ul>{passes.map((finding, index) =>
        <li key={`${finding.rule}-${index}`}>{finding.message}</li>,
      )}</ul>
    </details>
  </section>;
}
