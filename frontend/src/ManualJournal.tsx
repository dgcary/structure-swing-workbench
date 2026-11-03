import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  canUseManualJournal, parseManualJournal, type ManualJournalResponse,
} from "./manualJournalContract";
import { buildSellAllocations } from "./manualSellAllocation";

type LotForm = { symbol: string; quantity: string; paid_amount: string; bought_at: string };
type OperationForm = {
  side: "BUY" | "SELL"; symbol: string; quantity: string; price: string;
  executed_at: string; fee: string;
};

function localTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString().slice(0, 19);
}
function nowLocal(): string { return localTime(new Date().toISOString()); }
function utcTime(value: string): string {
  const date = new Date(value);
  if (!value || !Number.isFinite(date.getTime())) throw new Error("请填写有效的日期和时间。");
  return date.toISOString();
}
function errorFor(status: number): string {
  if (status === 404) return "手工台账尚未在家庭工作台中启用。";
  if (status === 401) return "访问口令不正确。";
  if (status === 403) return "手机访问需要可信 HTTPS；本机可使用回环地址。";
  if (status === 409) return "另一设备已保存新版本。当前填写内容没有被覆盖，请记下修改后重新读取。";
  if (status === 413) return "记录过大，请减少持仓批次或备注。";
  if (status === 422) return "录入与当前持仓不一致，请核对时间、证券、数量、金额和卖出批次。";
  return "手工台账服务暂不可用。";
}

export function ManualJournal() {
  const allowed = canUseManualJournal(window.location);
  const [token, setToken] = useState("");
  const [journal, setJournal] = useState<ManualJournalResponse | null>(null);
  const [observedAt, setObservedAt] = useState(nowLocal);
  const [cash, setCash] = useState("");
  const [equity, setEquity] = useState("");
  const [lots, setLots] = useState<LotForm[]>([]);
  const [operationObservedAt, setOperationObservedAt] = useState(nowLocal);
  const [afterCash, setAfterCash] = useState("");
  const [afterEquity, setAfterEquity] = useState("");
  const [sellAllocationQuantities, setSellAllocationQuantities] = useState<Record<number, string>>({});
  const [operation, setOperation] = useState<OperationForm>({
    side: "BUY", symbol: "", quantity: "", price: "", executed_at: nowLocal(), fee: "",
  });
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const requestId = useRef(0);

  useEffect(() => () => { requestId.current += 1; }, []);

  function prepare(data: ManualJournalResponse) {
    setObservedAt(nowLocal());
    setCash(data.latest?.available_cash ?? "");
    setEquity(data.latest?.total_equity ?? "");
    setLots(data.latest?.lots.map((lot) => ({
      symbol: lot.symbol, quantity: lot.quantity, paid_amount: lot.paid_amount ?? "",
      bought_at: localTime(lot.bought_at),
    })) ?? []);
    setOperationObservedAt(nowLocal());
    setAfterCash(""); setAfterEquity(""); setSellAllocationQuantities({});
    setOperation({ side: "BUY", symbol: "", quantity: "", price: "",
      executed_at: nowLocal(), fee: "" });
    setNote("");
  }

  async function read(accessToken: string, prefill: boolean): Promise<ManualJournalResponse> {
    const response = await fetch("/api/workbench/manual-journal", {
      headers: { "X-Workbench-Journal-Token": accessToken },
    });
    if (!response.ok) throw new Error(errorFor(response.status));
    const body: unknown = await response.json();
    const checked = parseManualJournal(body);
    if (prefill) prepare(checked);
    return checked;
  }

  async function connect() {
    if (!allowed) { setError("此页面未使用可信连接，已禁止发送口令。"); return; }
    if (token.length < 32) { setError("请输入家庭工作台的完整访问口令。"); return; }
    const active = ++requestId.current;
    setPending(true); setError(""); setMessage("");
    try {
      const checked = await read(token, true);
      if (active === requestId.current) {
        setJournal(checked);
        setMessage("已读取同一份服务端手工台账；下方表单已复制最新记录供修改。");
      }
    } catch (cause) {
      if (active === requestId.current) setError(cause instanceof Error ? cause.message : "读取失败。");
    } finally {
      if (active === requestId.current) setPending(false);
    }
  }

  function updateLot(index: number, change: Partial<LotForm>) {
    setLots((current) => current.map((row, at) => at === index ? { ...row, ...change } : row));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!journal || !allowed || token.length < 32) return;
    let payload: object;
    try {
      payload = {
        expected_revision: journal.latest_revision,
        observed_at: utcTime(observedAt),
        available_cash: cash.trim() || null, total_equity: equity.trim() || null,
        lots: lots.map((lot) => ({
          symbol: lot.symbol.trim().toUpperCase(), quantity: lot.quantity.trim(),
          paid_amount: lot.paid_amount.trim() || null,
          bought_at: lot.bought_at ? utcTime(lot.bought_at) : null,
        })),
        operation: null,
        note: note.trim(),
      };
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "日期或时间无效。");
      return;
    }
    const active = ++requestId.current;
    setPending(true); setError(""); setMessage("");
    let posted = false;
    try {
      const response = await fetch("/api/workbench/manual-journal", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Workbench-Journal-Token": token },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(errorFor(response.status));
      posted = true;
      const checked = await read(token, false);
      if (active === requestId.current) {
        setJournal(checked);
        prepare(checked);
        setMessage(`已保存第 ${checked.latest_revision} 版手工记录；家庭 HTTPS 入口配置后，手机和电脑可读取同一份台账。`);
      }
    } catch (cause) {
      if (active === requestId.current) setError(posted
        ? "记录已提交，但回读失败。请重新读取确认，避免重复提交。"
        : cause instanceof Error ? cause.message : "保存失败，表单内容仍在。");
    } finally {
      if (active === requestId.current) setPending(false);
    }
  }

  async function saveOperation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!journal?.latest || !allowed || token.length < 32) return;
    let payload: object;
    try {
      const allocations = operation.side === "SELL" ? buildSellAllocations(
        journal.latest.lots, operation.symbol, operation.quantity, sellAllocationQuantities,
      ) : null;
      payload = {
        expected_revision: journal.latest_revision,
        observed_at: utcTime(operationObservedAt),
        available_cash: afterCash.trim() || null,
        total_equity: afterEquity.trim() || null,
        sell_allocations: allocations,
        operation: {
          side: operation.side, symbol: operation.symbol.trim().toUpperCase(),
          quantity: operation.quantity.trim(), price: operation.price.trim(),
          executed_at: utcTime(operation.executed_at), fee: operation.fee.trim() || null,
        },
      };
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "日期或时间无效。"); return;
    }
    const active = ++requestId.current;
    setPending(true); setError(""); setMessage("");
    let posted = false;
    try {
      const response = await fetch("/api/workbench/manual-journal/operation", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Workbench-Journal-Token": token },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(errorFor(response.status));
      posted = true;
      const checked = await read(token, false);
      if (active === requestId.current) {
        setJournal(checked); prepare(checked);
        setMessage(`买卖已记入第 ${checked.latest_revision} 版，持仓数量由工作台自动更新；请核对新版本。`);
      }
    } catch (cause) {
      if (active === requestId.current) setError(posted
        ? "操作已提交，但回读失败。请重新读取确认，避免重复提交。"
        : cause instanceof Error ? cause.message : "操作未保存，表单内容仍在。");
    } finally {
      if (active === requestId.current) setPending(false);
    }
  }

  const sellOptions = journal?.latest?.lots.map((lot, index) => ({ lot, index }))
    .filter(({ lot }) => lot.symbol === operation.symbol.trim().toUpperCase()) ?? [];

  return <section className="panel manual-journal-panel">
    <h2>手工账户台账</h2>
    <p className="notice">只记录你填写的资金、持仓批次和买卖操作。买入金额是手工登记的投入金额，不是当前市值；记录不与券商自动对账，也不产生交易许可。</p>
    {!allowed && <p role="alert">当前网页是局域网明文连接。为保护账户记录，手机需通过可信 HTTPS 打开工作台。</p>}
    <label>家庭工作台访问口令
      <input type="password" autoComplete="off" disabled={pending} value={token} onChange={(event) => {
        requestId.current += 1; setPending(false); setJournal(null); setToken(event.target.value);
        setError(""); setMessage("");
      }} />
    </label>
    <button type="button" disabled={!allowed || pending || !token} onClick={() => { void connect(); }}>
      {pending ? "正在处理…" : "读取手工台账"}
    </button>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {journal && <>
      <p className="notice">当前共 {journal.total_revisions} 个版本；最新第 {journal.latest_revision} 版。每次保存是完整的新快照，旧版保留。</p>
      <form className="manual-journal-form" onSubmit={(event) => { void save(event); }}>
        <h3>初次对齐仓位／人工校正</h3>
        <label>你核对账户的时间
          <input type="datetime-local" step="1" required value={observedAt} onChange={(event) => setObservedAt(event.target.value)} />
        </label>
        <label>可用资金（元；不知道可留空）
          <input type="text" inputMode="decimal" value={cash} onChange={(event) => setCash(event.target.value)} />
        </label>
        <label>账户总权益（元；不知道可留空）
          <input type="text" inputMode="decimal" value={equity} onChange={(event) => setEquity(event.target.value)} />
        </label>
        <h3>当前持仓买入批次</h3>
        <p className="notice">从上一版复制而来。首次请按券商页面对齐；买卖操作请使用下方独立表单，系统会自动增减数量。这里也可人工校正记录。</p>
        {lots.map((lot, index) => <div className="manual-journal-lot" key={index}>
          <label>证券代码<input type="text" maxLength={16} required value={lot.symbol}
            onChange={(event) => updateLot(index, { symbol: event.target.value })} /></label>
          <label>当前持有数量<input type="text" inputMode="decimal" required value={lot.quantity}
            onChange={(event) => updateLot(index, { quantity: event.target.value })} /></label>
          <label>这批持仓的投入金额（元；未知可留空）<input type="text" inputMode="decimal" value={lot.paid_amount}
            onChange={(event) => updateLot(index, { paid_amount: event.target.value })} /></label>
          <label>买入时间（可留空）<input type="datetime-local" step="1" value={lot.bought_at}
            onChange={(event) => updateLot(index, { bought_at: event.target.value })} /></label>
          <button type="button" onClick={() => setLots((current) => current.filter((_, at) => at !== index))}>删除这批持仓</button>
        </div>)}
        <button type="button" onClick={() => setLots((current) => [...current,
          { symbol: "", quantity: "", paid_amount: "", bought_at: "" }])}>增加一批持仓</button>
        <label>备注（可选）<textarea maxLength={200} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        <button type="submit" disabled={pending}>保存当前仓位为新版本</button>
      </form>
      {journal.latest && <form className="manual-journal-form" onSubmit={(event) => { void saveOperation(event); }}>
        <h3>录入买卖 · 自动更新持仓数量</h3>
        <p className="notice">买入会增加一批持仓；卖出请填写各买入批次的扣减数量，合计须等于卖出总数。只有一批时可留空，自动扣减全部卖出数量。操作后资金未知时留空，不延用旧资金。</p>
        <label>操作后查看账户的时间
          <input type="datetime-local" step="1" required value={operationObservedAt}
            onChange={(event) => setOperationObservedAt(event.target.value)} />
        </label>
        <div className="manual-journal-lot">
          <label>方向<select value={operation.side} onChange={(event) => {
            setOperation((current) => ({ ...current, side: event.target.value as "BUY" | "SELL" }));
            setSellAllocationQuantities({});
          }}><option value="BUY">买入</option><option value="SELL">卖出</option></select></label>
          <label>证券代码<input type="text" required maxLength={16} value={operation.symbol}
            onChange={(event) => { setOperation((current) => ({ ...current, symbol: event.target.value })); setSellAllocationQuantities({}); }} /></label>
          <label>成交数量<input type="text" required inputMode="decimal" value={operation.quantity}
            onChange={(event) => setOperation((current) => ({ ...current, quantity: event.target.value }))} /></label>
          <label>成交价格<input type="text" required inputMode="decimal" value={operation.price}
            onChange={(event) => setOperation((current) => ({ ...current, price: event.target.value }))} /></label>
          <label>成交时间<input type="datetime-local" step="1" required value={operation.executed_at}
            onChange={(event) => setOperation((current) => ({ ...current, executed_at: event.target.value }))} /></label>
          <label>费用（未知可留空）<input type="text" inputMode="decimal" value={operation.fee}
            onChange={(event) => setOperation((current) => ({ ...current, fee: event.target.value }))} /></label>
        </div>
        {operation.side === "SELL" && sellOptions.map(({ lot, index }) =>
          <label key={index}>第 {index + 1} 批 · 持有 {lot.quantity} 股 · 买入 {lot.bought_at ?? "时间未知"} · 本次扣减数量
            <input type="text" inputMode="decimal" value={sellAllocationQuantities[index] ?? ""}
              placeholder={sellOptions.length === 1 ? "留空则扣减本次卖出总数" : "不扣减可留空"}
              onChange={(event) => setSellAllocationQuantities((current) => ({
                ...current, [index]: event.target.value,
              }))} />
          </label>)}
        {operation.side === "SELL" && sellOptions.length === 0 &&
          <p role="alert">当前版本找不到这只证券的持仓批次，请先核对证券代码或校正仓位。</p>}
        <label>操作后可用资金（元；未知可留空）
          <input type="text" inputMode="decimal" value={afterCash} onChange={(event) => setAfterCash(event.target.value)} />
        </label>
        <label>操作后账户总权益（元；未知可留空）
          <input type="text" inputMode="decimal" value={afterEquity} onChange={(event) => setAfterEquity(event.target.value)} />
        </label>
        <button type="submit" disabled={pending || (operation.side === "SELL" && sellOptions.length === 0)}>
          记录操作并自动更新持仓
        </button>
      </form>}
      <h3>最近记录</h3>
      {journal.history.length === 0 ? <p>尚未登记；不代表账户为空。</p> :
        journal.history.map((record) => <details key={record.id} className="manual-journal-history">
          <summary>第 {record.revision} 版 · 核对于 {record.observed_at} · {record.lots.length} 批持仓</summary>
          <p>服务端保存：{record.recorded_at} · 来源：用户手工记录，未经券商核对</p>
          <p>可用资金：{record.available_cash ?? "未填写"} 元 · 总权益：{record.total_equity ?? "未填写"} 元</p>
          {record.operation && <p>操作：{record.operation.side === "BUY" ? "买入" : "卖出"} {record.operation.symbol} · {record.operation.quantity} 股 · 价格 {record.operation.price} 元 · {record.operation.executed_at} · 费用 {record.operation.fee ?? "未知"}</p>}
          {record.lots.map((lot, index) => <p key={index}>{lot.symbol} · {lot.quantity} 股 · 登记投入 {lot.paid_amount ?? "未知"} 元 · 买入 {lot.bought_at ?? "时间未知"}</p>)}
          {record.note && <p>备注：{record.note}</p>}
        </details>)}
      {journal.total_revisions > journal.history.length && <p>仅显示最近 {journal.history.length} 版；较早记录仍保存在服务端。</p>}
    </>}
  </section>;
}
