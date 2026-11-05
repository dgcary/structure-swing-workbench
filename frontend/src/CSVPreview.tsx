import { useEffect, useRef, useState, type FormEvent } from "react";
import { csvPreviewVerdict } from "./csvPreviewVerdict";

type CSVKind = "fills" | "holdings" | "account";
type Preview = {
  schema_version: string;
  kind: CSVKind;
  row_count: number;
  new_facts_in_isolated_preview: number;
  duplicates_in_isolated_preview: number;
  conflicts_in_isolated_preview: number;
  valid_csv_structure: boolean;
  persisted: false;
  reconciled_with_live_account: false;
  trade_execution_enabled: false;
  notice: string;
};

const columns: Record<CSVKind, string> = {
  fills: "fill_id,symbol,side,quantity,price,executed_at",
  holdings: "symbol,quantity,cost,as_of",
  account: "equity,available_cash,as_of",
};

export function CSVPreview() {
  const [kind, setKind] = useState<CSVKind>("fills");
  const [data, setData] = useState("");
  const [result, setResult] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const requestVersion = useRef(0);
  const fileVersion = useRef(0);
  useEffect(() => () => { requestVersion.current++; fileVersion.current++; }, []);
  function invalidate() {
    requestVersion.current++;
    fileVersion.current++;
    setResult(null);
    setError("");
    setPending(false);
  }

  async function loadFile(file?: File) {
    invalidate();
    setData("");
    if (!file) return;
    if (file.size > 500_000) {
      setError("文件超过 500 KB，未读取。");
      return;
    }
    const activeRead = fileVersion.current;
    try { const csv = await file.text(); if (activeRead === fileVersion.current) setData(csv); }
    catch { if (activeRead === fileVersion.current) setError("读取文件失败，请粘贴 CSV 内容。"); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const activeRequest = ++requestVersion.current;
    const submittedKind = kind;
    setResult(null);
    setError("");
    setPending(true);
    try {
      const response = await fetch("/api/workbench/csv-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: submittedKind, data }),
      });
      const body = await response.json();
      if (activeRequest !== requestVersion.current) return;
      if (!response.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : "CSV 格式校验失败");
      }
      const preview = body as Preview;
      if (preview.schema_version !== "m8.csv_preview.v1" ||
          preview.kind !== submittedKind ||
          preview.persisted !== false ||
          preview.reconciled_with_live_account !== false ||
          preview.trade_execution_enabled !== false) {
        throw new Error("校验结果协议异常；禁止当作正式导入。");
      }
      // Invalid counters and conflicting facts must never be displayed as a clean import.
      csvPreviewVerdict(preview);
      setResult(preview);
    } catch (cause) {
      if (activeRequest === requestVersion.current) setError(cause instanceof Error ? cause.message : "请求失败");
    } finally { if (activeRequest === requestVersion.current) setPending(false); }
  }

  const verdict = result === null ? null : csvPreviewVerdict(result);
  return <section className="panel">
    <h2>成交与账户 CSV · 导入前校验</h2>
    <p className="notice">仅在临时空白账本检查格式及内部冲突。不保存、不导入、不核对真实账户；校验成功不代表账户数据已更新。</p>
    <form className="csv-preview-form" onSubmit={submit}>
      <label>文件类型
        <select value={kind} onChange={(e) => {
          invalidate(); setKind(e.target.value as CSVKind); setData("");
        }}>
          <option value="fills">确认成交</option>
          <option value="holdings">持仓快照</option>
          <option value="account">账户快照</option>
        </select>
      </label>
      <p>必填表头：<code>{columns[kind]}</code>；时间须为含时区的 ISO8601。</p>
      <label>选择本地 CSV 文件
        <input type="file" accept=".csv,text/csv" onChange={(e) => {
          void loadFile(e.target.files?.[0]);
        }} />
      </label>
      <label>CSV 内容（可直接粘贴）
        <textarea required maxLength={500_000} value={data} onChange={(e) => {
          invalidate(); setData(e.target.value);
        }} />
      </label>
      <button type="submit" disabled={pending || !data.trim()}>
        {pending ? "校验中…" : "仅校验，不导入"}
      </button>
    </form>
    {error && <p role="alert">校验失败：{error}</p>}
    {result && verdict && <section className="plan-result" role={verdict.level === "ok" ? "status" : "alert"}>
      <strong>{verdict.heading}</strong>
      <p>输入行数：{result.row_count}；临时账本新增事实：{result.new_facts_in_isolated_preview}；
        重复：{result.duplicates_in_isolated_preview}；冲突：{result.conflicts_in_isolated_preview}</p>
      <p>{verdict.explanation}</p>
      <p>{result.notice}</p>
    </section>}
  </section>;
}
