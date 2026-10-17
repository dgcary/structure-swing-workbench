import { useRef, useState, type FormEvent } from "react";

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
};

const fields: { key: Kind; title: string; columns: string }[] = [
  { key: "account", title: "账户快照", columns: "equity,available_cash,as_of" },
  { key: "holdings", title: "持仓快照", columns: "symbol,quantity,cost,as_of" },
  { key: "fills", title: "确认成交", columns: "fill_id,symbol,side,quantity,price,executed_at" },
];

export function AccountSnapshotPreview({
  onPreview, onReset,
}: {
  onPreview: (snapshot: SnapshotOverview) => void;
  onReset: () => void;
}) {
  const [values, setValues] = useState<CSVValues>({ account: "", holdings: "", fills: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const requestId = useRef(0);
  const fileReadId = useRef<Record<Kind, number>>({ account: 0, holdings: 0, fills: 0 });

  function invalidatePreview() {
    requestId.current += 1;
    setPending(false);
    setError("");
    setNotice("");
    onReset();
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
    const supplied = Object.fromEntries(
      fields.filter(({ key }) => values[key].trim()).map(({ key }) => [key, values[key]])
    );
    if (!Object.keys(supplied).length) {
      setError("请至少提供一份 CSV。");
      return;
    }
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
      if (activeRequest === requestId.current) {
        onPreview(result);
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
      <button type="submit" disabled={pending || !Object.values(values).some((value) => value.trim())}>
        {pending ? "正在核验…" : "预览本次账户与持仓"}
      </button>
    </form>
    {error && <p role="alert">预览失败：{error}</p>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
