import { useCallback, useEffect, useState } from "react";
import type { KLineData } from "klinecharts";
import type { MarketResultDto } from "../api";
import { api, qualityName } from "../api";
import { CandlestickChart } from "./CandlestickChart";

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

const timeframes: { value: string; label: string }[] = [
  { value: "1d", label: "日K" },
  { value: "15m", label: "15分钟" },
  { value: "5m", label: "5分钟" },
];

function toKLineData(payload: MarketResultDto): KLineData[] {
  if (!Array.isArray(payload.value)) return [];
  return payload.value
    .map((raw) => {
      const bar = raw as Record<string, unknown>;
      const observedAt = typeof bar.observed_at === "string" ? bar.observed_at : null;
      const timestamp = observedAt === null ? NaN : Date.parse(observedAt);
      return {
        timestamp,
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
        volume: bar.volume === undefined || bar.volume === null ? undefined : Number(bar.volume),
        turnover:
          bar.amount === undefined || bar.amount === null ? undefined : Number(bar.amount),
      };
    })
    .filter((bar) => Number.isFinite(bar.timestamp) && Number.isFinite(bar.close));
}

export function MarketSection({ backendReady }: { backendReady: boolean }) {
  const [symbol, setSymbol] = useState("600000");
  const [timeframe, setTimeframe] = useState("1d");
  const [quote, setQuote] = useState<MarketResultDto | null>(null);
  const [bars, setBars] = useState<MarketResultDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const code = symbol.trim();
      const [quoteResult, barsResult] = await Promise.all([
        api.marketQuote(code),
        api.marketBars(code, timeframe),
      ]);
      setQuote(quoteResult);
      setBars(barsResult);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!backendReady) return;
    void load();
  }, [backendReady, load]);

  const value = quote?.value;
  const quoteValue = value && !Array.isArray(value) ? value : null;
  const kLineData = bars ? toKLineData(bars) : [];

  return (
    <section className="section">
      <div className="panel">
        <div className="panel-heading">
          <h2>行情查询</h2>
          <span className="muted">K 线来自行情适配器；缺失数据不会以假数据冒充。</span>
        </div>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <label>
            证券代码
            <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
          </label>
          <div className="timeframe-picker" role="group" aria-label="K线周期">
            {timeframes.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`tab ${timeframe === item.value ? "active" : ""}`}
                onClick={() => setTimeframe(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
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

      {bars && (
        <div className="panel">
          <div className="panel-heading">
            <h2>K 线（{timeframes.find((item) => item.value === timeframe)?.label ?? timeframe}）</h2>
            <span className={`badge ${bars.quality === "FRESH" ? "risk-pass" : "risk-warning"}`}>
              {qualityName(bars.quality)}
            </span>
          </div>
          {bars.error && <p className="muted">来源提示：{bars.error}</p>}
          {kLineData.length === 0 ? (
            <p>暂无 K 线数据；部署环境需安装 akshare（market 可选依赖）。</p>
          ) : (
            <CandlestickChart bars={kLineData} />
          )}
        </div>
      )}
    </section>
  );
}
