import { useEffect, useRef, useState, type FormEvent } from "react";
import { assertReadOnlyOverview } from "./overviewContract";
import {
  buildDailyFillClaim, parseDailyCoverage,
  type DailyClaimInput, type DailyCoverage, type DailyFillClaim,
} from "./dailyFillClaim";

type Kind = "account" | "holdings" | "fills";
type CSVValues = Record<Kind, string>;

export type SnapshotOverview = {
  schema_version: "m8.account_snapshot_preview.v1";
  mode: "isolated_csv_preview";
  input_source: "user_uploaded_csv";
  persisted: false;
  realtime: false;
  full_account_verified: false;
  trade_execution_enabled: false;
  imported_kinds: Kind[];
  notice: string;
  metrics: {
    key: string; label: string; unit: string; value: string | null;
    status: "available" | "unavailable"; source: string | null; as_of: string | null;
  }[];
  holdings: {
    symbol: string; status: "snapshot" | "partial" | "unanchored" | "conflict";
    quantity: string | null; broker_display_cost: string | null;
    core_quantity: string | null; t_quantity: string | null;
    source: string | null; as_of: string | null; warning: string;
  }[] | null;
  effective_plans: null;
  pending_actions: null;
  audit_results: null;
  daily_fill_coverage: DailyCoverage | null;
};

const fields: { key: Kind; title: string; columns: string }[] = [
  { key: "account", title: "账户快照", columns: "equity,available_cash,as_of" },
  { key: "holdings", title: "持仓快照", columns: "symbol,quantity,cost,as_of" },
  { key: "fills", title: "确认成交", columns: "fill_id,symbol,side,quantity,price,executed_at" },
];

const emptyClaim: DailyClaimInput = {
  enabled: false, marketDate: "", exportedAt: "", completeThrough: "",
  exportReference: "", fillIds: "", declaredFullDay: false,
};

export function AccountSnapshotPreview({
  onPreview, onReset,
}: {
  onPreview: (snapshot: SnapshotOverview) => void;
  onReset: () => void;
}) {
  const [values, setValues] = useState<CSVValues>({ account: "", holdings: "", fills: "" });
  const [claim, setClaim] = useState<DailyClaimInput>(emptyClaim);
  const [coverage, setCoverage] = useState<DailyCoverage | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const requestId = useRef(0);
  const fileReadId = useRef<Record<Kind, number>>({ account: 0, holdings: 0, fills: 0 });

  // Discard responses and file reads from a form that has been unmounted.
  useEffect(() => () => {
    requestId.current += 1;
    fileReadId.current.account += 1;
    fileReadId.current.holdings += 1;
    fileReadId.current.fills += 1;
  }, []);

  function invalidatePreview() {
    requestId.current += 1;
    setPending(false);
    setError("");
    setNotice("");
    setCoverage(null);
    onReset();
  }

  function changeClaim(change: Partial<DailyClaimInput>) {
    invalidatePreview();
    setClaim((previous) => ({ ...previous, ...change }));
  }

  function change(kind: Kind, value: string) {
    fileReadId.current[kind] += 1;
    invalidatePreview();
    setValues((previous) => ({ ...previous, [kind]: value }));
  }

  async function load(kind: Kind, file?: File) {
    const activeRead = ++fileReadId.current[kind];
    invalidatePreview();
    setValues((previous) => ({ ...previous, [kind]: "" }));
    if (!file) return;
    if (file.size > 500_000) {
      setError("单个 CSV 不得超过 500 KB；文件未读取。");
      return;
    }
    try {
      const content = await file.text();
      if (activeRead !== fileReadId.current[kind]) return;
      invalidatePreview();
      setValues((previous) => ({ ...previous, [kind]: content }));
    } catch {
      if (activeRead === fileReadId.current[kind]) setError("读取本地 CSV 失败，请粘贴内容。");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    const supplied: Record<string, string | DailyFillClaim> = Object.fromEntries(
      fields.filter(({ key }) => values[key].trim()).map(({ key }) => [key, values[key]])
    );
    if (!Object.keys(supplied).length) {
      setError("请至少提供一份 CSV。");
      return;
    }
    let dailyClaim;
    try {
      dailyClaim = buildDailyFillClaim(claim, Boolean(values.fills.trim()));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "逐日成交清单无效。");
      return;
    }
    if (dailyClaim) supplied.daily_fill_claim = dailyClaim;
    const activeRequest = ++requestId.current;
    setPending(true);
    onReset();
    try {
      const response = await fetch("/api/workbench/account-snapshot-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(supplied),
      });
      const body: unknown = await response.json();
      if (!response.ok) {
        const detail = (body && typeof body === "object" && "detail" in body)
          ? (body as { detail: unknown }).detail : null;
        throw new Error(typeof detail === "string" ? detail : "账户快照校验失败");
      }
      assertReadOnlyOverview(body, "isolated_csv_preview");
      const result = body as SnapshotOverview;
      if (result.schema_version !== "m8.account_snapshot_preview.v1" ||
          result.mode !== "isolated_csv_preview" ||
          result.input_source !== "user_uploaded_csv" ||
          result.persisted !== false || result.realtime !== false ||
          result.full_account_verified !== false || result.trade_execution_enabled !== false ||
          !Array.isArray(result.metrics) ||
          !(result.holdings === null || Array.isArray(result.holdings))) {
        throw new Error("快照协议不匹配，禁止当作真实账户数据。");
      }
      const checkedCoverage = parseDailyCoverage(result.daily_fill_coverage, Boolean(dailyClaim));
      if (activeRequest === requestId.current) {
        onPreview(result);
        setCoverage(checkedCoverage);
        setNotice("临时快照已显示在下方总览；不保存、不代表账户全量或实时数据。");
      }
    } catch (cause) {
      if (activeRequest === requestId.current) {
        setError(cause instanceof Error ? cause.message : "预览失败");
      }
    } finally {
      if (activeRequest === requestId.current) setPending(false);
    }
  }

  return <section className="panel">
    <h2>本地 CSV · 临时账户总览</h2>
    <p className="notice">只处理本次主动提供的文件，不连接券商、不保存。未提供的字段继续显示“未接入”，不推断空仓或账户风险。</p>
    <form className="csv-preview-form" onSubmit={(event) => { void submit(event); }}>
      {fields.map(({ key, title, columns }) => (
        <div className="snapshot-input" key={key}>
          <label>{title}（可选）
            <input type="file" accept=".csv,text/csv" onChange={(event) => {
              void load(key, event.target.files?.[0]);
            }} />
          </label>
          <p>表头：<code>{columns}</code>；时间须包含时区。</p>
          <label>{title} CSV 内容（可粘贴）
            <textarea maxLength={500_000} value={values[key]} onChange={(event) => {
              change(key, event.target.value);
            }} />
          </label>
        </div>
      ))}
      <details className="daily-claim-input">
        <summary>可选：逐日成交清单对照（仅用户自报）</summary>
        <p>将自报成交编号与本次上传 CSV 核对。两份材料都由你提供；即使一致，也不能证明券商全量成交、T+1 可卖数量或交易许可。</p>
        <label className="claim-check">
          <input type="checkbox" checked={claim.enabled} onChange={(event) => {
            changeClaim({ enabled: event.target.checked });
          }} />启用本次逐日对照
        </label>
        {claim.enabled && <div className="daily-claim-fields">
          <label>交易日（上海市场日期，如 2026-10-16）
            <input type="text" value={claim.marketDate} onChange={(event) => {
              changeClaim({ marketDate: event.target.value });
            }} />
          </label>
          <label>清单导出时间（含时区，如 2026-10-16T16:00:00+08:00）
            <input type="text" value={claim.exportedAt} onChange={(event) => {
              changeClaim({ exportedAt: event.target.value });
            }} />
          </label>
          <label>成交覆盖至（含时区，如 2026-10-16T15:30:00+08:00）
            <input type="text" value={claim.completeThrough} onChange={(event) => {
              changeClaim({ completeThrough: event.target.value });
            }} />
          </label>
          <label>自报导出编号
            <input type="text" maxLength={128} value={claim.exportReference} onChange={(event) => {
              changeClaim({ exportReference: event.target.value });
            }} />
          </label>
          <label>自报成交编号（每行一个）
            <textarea value={claim.fillIds} onChange={(event) => {
              changeClaim({ fillIds: event.target.value });
            }} />
          </label>
          <label className="claim-check">
            <input type="checkbox" checked={claim.declaredFullDay} onChange={(event) => {
              changeClaim({ declaredFullDay: event.target.checked });
            }} />自报清单覆盖该交易日全天
          </label>
        </div>}
      </details>
      <button type="submit" disabled={pending || !Object.values(values).some((value) => value.trim())}>
        {pending ? "正在核验…" : "预览本次账户与持仓"}
      </button>
    </form>
    {error && <p role="alert">预览失败：{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {coverage && <section className="plan-result" role={coverage.status === "mismatch" ? "alert" : "status"}>
      <strong>{coverage.status === "mismatch" ? "自报清单与 CSV 不一致" :
        coverage.status === "matched_unverified" ? "自报清单与 CSV 一致 · 未认证" :
        "逐日覆盖证据不足"}</strong>
      <p>交易日：{coverage.market_date}；自报 {coverage.declared_fill_count} 笔，上传 {coverage.recorded_fill_count} 笔；
        缺失 {coverage.missing_fill_count} 笔，额外 {coverage.unexpected_fill_count} 笔，重复行 {coverage.duplicate_csv_rows} 行。</p>
      {coverage.missing_fill_ids.length > 0 && <p>自报有、上传缺失：
        {coverage.missing_fill_ids.slice(0, 20).join("、")}
        {coverage.missing_fill_ids.length > 20 ? " 等（仅显示前 20 笔）" : ""}</p>}
      {coverage.unexpected_fill_ids.length > 0 && <p>上传有、自报未列：
        {coverage.unexpected_fill_ids.slice(0, 20).join("、")}
        {coverage.unexpected_fill_ids.length > 20 ? " 等（仅显示前 20 笔）" : ""}</p>}
      <p>水位外成交 {coverage.outside_watermark_fill_count} 笔；其他日期成交 {coverage.outside_claimed_day_fill_count} 笔。</p>
      <p>{coverage.warning}</p>
      <p>券商全量未认证 · 不可据此交易</p>
    </section>}
  </section>;
}
