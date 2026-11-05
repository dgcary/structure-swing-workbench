import { useEffect, useRef, useState } from "react";
import {
  canUploadLocalStatement, localStatementEndpoint, parseDongwuStatementCheck,
  type DongwuStatementCheck,
} from "./dongwuStatementContract";

const maxBytes = 10_000_000;

function responseError(status: number): string {
  if (status === 404) return "本机账单核对功能尚未启用。";
  if (status === 403) return "账单仅可在本机工作台中核对。";
  if (status === 413) return "PDF 超过 10 MB，未进行核对。";
  if (status === 415) return "请选择已解压的 PDF，不要上传 ZIP。";
  if (status === 422) return "无法识别或核对这份东吴 PDF；未采信其中的数据。";
  if (status === 503) return "本机缺少 PDF 核对组件。";
  return "核对服务暂不可用。";
}

export function DongwuStatementPreview() {
  const localPage = canUploadLocalStatement(window.location);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<DongwuStatementCheck | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const requestId = useRef(0);

  useEffect(() => () => { requestId.current += 1; }, []);

  function choose(next: File | null) {
    requestId.current += 1;
    setPending(false);
    setResult(null);
    setError("");
    if (!next) { setFile(null); return; }
    if (!next.name.toLowerCase().endsWith(".pdf") ||
        (next.type && next.type !== "application/pdf")) {
      setFile(null);
      setError("请选择已解压的 PDF，不要上传 ZIP。");
      return;
    }
    if (next.size === 0 || next.size > maxBytes) {
      setFile(null);
      setError("PDF 必须非空且不超过 10 MB。");
      return;
    }
    setFile(next);
  }

  async function check() {
    if (!file) return;
    if (!canUploadLocalStatement(window.location)) {
      setError("仅可在本机打开工作台并选择 PDF；未发送文件。");
      return;
    }
    const active = ++requestId.current;
    setPending(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(localStatementEndpoint, {
        method: "POST", headers: { "Content-Type": "application/pdf" }, body: file,
      });
      if (!response.ok) throw new Error(responseError(response.status));
      const payload: unknown = await response.json();
      const checked = parseDongwuStatementCheck(payload);
      if (active === requestId.current) setResult(checked);
    } catch (cause) {
      if (active === requestId.current) {
        setError(cause instanceof Error ? cause.message : "核对失败。");
      }
    } finally {
      if (active === requestId.current) setPending(false);
    }
  }

  return <section className="panel">
    <h2>东吴 PDF · 历史账单核对</h2>
    <p className="notice">请先在本机解压 ZIP，只选择其中的 PDF。密码不输入工作台；所选 PDF 仅发送到你本机启用的工作台服务，当次核对后不保存。</p>
    <p className="notice">此功能默认关闭。核对只比较账单内部的明细和合计，不会更新实时账户、持仓、T 次数或交易权限。</p>
    {!localPage && <p role="status">此页面不是本机地址，PDF 上传已禁用。</p>}
    {localPage && <label>选择已解压的 PDF
      <input type="file" accept=".pdf,application/pdf" onChange={(event) => {
        choose(event.target.files?.[0] ?? null);
      }} />
    </label>}
    <button type="button" disabled={!localPage || !file || pending} onClick={() => { void check(); }}>
      {pending ? "正在核对…" : "仅核对这份账单"}
    </button>
    {file && <p role="status">已选择 PDF；文件名和交易内容不会显示在结果中。</p>}
    {error && <p role="alert">{error}</p>}
    {result && <div role="status" className="audit-unknown">
      <strong>{result.status === "matched_unverified" ? "账单内部一致 · 尚未认证" : "账单内部存在差异"}</strong>
      <p>账单周期：{result.period_start} 至 {result.period_end}</p>
      <p>成交汇总 {result.summary_row_count} 行；交割明细 {result.detail_row_count} 行；一致分组 {result.matched_group_count} 组。</p>
      <p>缺失汇总 {result.missing_summary_group_count} 组；多余汇总 {result.extra_summary_group_count} 组；分组差异 {result.mismatched_group_count} 组；币种合计差异 {result.footer_totals_mismatched_count} 处。</p>
      <p>跨页恢复 {result.repaired_summary_rows} 行；两张表的币种合计均已核对。</p>
      <p>缺逐笔成交编号、成交时刻及逐日完整性证明，不能作为实时账户或交易依据。</p>
    </div>}
  </section>;
}
