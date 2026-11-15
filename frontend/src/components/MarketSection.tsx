import { useState } from "react";
import type { MarketResultDto } from "../api";
import { api, qualityName } from "../api";

const quoteFields: { key: string; label: string }[] = [
  { key: "name", label: "名称" },
  { key: "last", label: "最新价" },
  { key: "previous_close", label: "昨收" },
  { key: "open", label: "今开" },
  { key: "high", label: "最高" },
  { key: "low", label: "最低" },
  { key: "change_pct", label: "涨跌幅" },
  { key: "volume", label: "成交量" },
  { key: "amount", label: "成交额" },
  { key: "turnover_pct", label: "换手率" },
];

export function MarketSection({ backendReady }: { backendReady: boolean }) {
  const [symbol, setSymbol] = useState("600000");
  const [quote, setQuote] = useState<MarketResultDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadQuote = async () => {
    setBusy(true);
    try {
      setQuote(await api.marketQuote(symbol.trim()));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const value = quote?.value;
  const quoteValue = value && !Array.isArray(value) ? value : null;

  return (
    <section className="section">
      <div className="panel">
        <div className="panel-heading">
          <h2>行情查询</h2>
          <span className="muted">K 线图表将在后续里程碑接入 KLineChart。</span>
        </div>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            void loadQuote();
          }}
        >
          <label>
            证券代码
            <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
          </label>
          <button type="submit" disabled={busy || !backendReady}>
            查询行情
          </button>
        </form>
      </div>

      {error && (
        <p role="alert" className="alert">
          行情查询失败：{error}
        </p>
      )}

      {quote && (
        <div className="panel">
          <div className="panel-heading">
            <h2>实时报价</h2>
            <span className={`badge ${quote.quality === "FRESH" ? "risk-pass" : "risk-warning"}`}>
              {qualityName(quote.quality)}
            </span>
          </div>
          <p className="muted">
            来源：{quote.source}；抓取时间：{quote.fetched_at ?? "—"}；观测时间：
            {quote.observed_at ?? "未提供"}
          </p>
          {quoteValue === null && <p>暂无报价数据。{quote.error ? `（${quote.error}）` : ""}</p>}
          {quoteValue !== null && (
            <dl className="facts">
              {quoteFields.map((field) => (
                <div key={field.key}>
                  <dt>{field.label}</dt>
                  <dd>{quoteValue[field.key] === undefined ? "—" : String(quoteValue[field.key])}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </section>
  );
}
