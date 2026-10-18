import { useEffect, useRef, useState, type FormEvent } from "react";

type Bar = { time: string; open: string; high: string; low: string; close: string; volume: string };
type Preview = {
  schema_version: string; source: string; timeframe: string; last_observation: string;
  bars: Bar[]; bar_count: number; persisted: boolean; realtime: boolean;
  setup_detected: boolean; trade_execution_enabled: boolean; notice: string;
};

function Chart({ bars }: { bars: Bar[] }) {
  const shown = bars.slice(-100);
  const high = Math.max(...shown.map((bar) => Number(bar.high)));
  const low = Math.min(...shown.map((bar) => Number(bar.low)));
  const pad = Math.max((high - low) * 0.05, high * 0.005);
  const y = (price: number) => 15 + (high + pad - price) / (high - low + 2 * pad) * 270;
  const step = 800 / shown.length;
  return <svg viewBox="0 0 860 320" role="img" aria-label="用户上传的非实时历史K线图">
    {shown.map((bar, index) => {
      const x = 40 + (index + 0.5) * step;
      const open = Number(bar.open), close = Number(bar.close);
      const top = y(Math.max(open, close)), bottom = y(Math.min(open, close));
      return <g key={bar.time} className={close >= open ? "candle-up" : "candle-down"}>
        <title>{bar.time} 开{bar.open} 高{bar.high} 低{bar.low} 收{bar.close}</title>
        <line x1={x} x2={x} y1={y(Number(bar.high))} y2={y(Number(bar.low))} />
        <rect x={x - Math.min(step * 0.3, 5)} y={top}
          width={Math.min(step * 0.6, 10)} height={Math.max(1, bottom - top)} />
      </g>;
    })}
    <text x="40" y="309" className="chart-axis">{shown[0].time}</text>
    <text x="850" y="309" textAnchor="end" className="chart-axis">{shown[shown.length - 1].time}</text>
  </svg>;
}

export function KlinePreview() {
  const [timeframe, setTimeframe] = useState("day");
  const [data, setData] = useState("");
  const [result, setResult] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const version = useRef(0);
  useEffect(() => () => { version.current++; }, []);
  const invalidate = () => { version.current++; setResult(null); setError(""); setPending(false); };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const current = ++version.current; setResult(null); setError(""); setPending(true);
    try {
      const response = await fetch("/api/workbench/kline-preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeframe, data }),
      });
      const payload = await response.json();
      if (current !== version.current) return;
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "CSV校验失败");
      const value = payload as Preview;
      if (value.schema_version !== "m8.kline_preview.v1" || value.source !== "user_uploaded_csv" ||
          value.persisted || value.realtime || value.setup_detected || value.trade_execution_enabled ||
          !Array.isArray(value.bars) || !value.bars.length ||
          value.bar_count !== value.bars.length || value.timeframe !== timeframe ||
          value.last_observation !== value.bars[value.bars.length - 1].time ||
          !value.bars.every((bar) => [bar.open, bar.high, bar.low, bar.close, bar.volume]
            .every((raw) => raw.trim() !== "" && Number.isFinite(Number(raw))) &&
            [bar.open, bar.high, bar.low, bar.close].every((raw) => Number(raw) > 0) &&
            Number(bar.volume) >= 0)) throw new Error("K线数据协议异常或超出浏览器可绘制范围");
      setResult(value);
    } catch (cause) { if (current === version.current) setError(cause instanceof Error ? cause.message : "读取失败"); }
    finally { if (current === version.current) setPending(false); }
  }
  return <section className="panel">
    <h2>K线 · 本地历史数据</h2>
    <p className="notice">只显示用户提供的OHLCV；非实时、不保存、不判断Setup或买卖。</p>
    <form className="csv-preview-form" onSubmit={submit}>
      <label>周期<select value={timeframe} onChange={(e) => { invalidate(); setTimeframe(e.target.value); }}>
        <option value="day">日K</option><option value="5m">5分钟</option><option value="15m">15分钟</option>
      </select></label>
      <p>表头：<code>time,open,high,low,close,volume</code>。分钟K时间须带时区，最多500根。</p>
      <label>选择CSV<input type="file" accept=".csv,text/csv" onChange={async (e) => {
        const file = e.target.files?.[0]; invalidate(); const current = version.current; setData("");
        if (!file) return;
        if (file.size > 250_000) { setError("文件超过250 KB"); return; }
        try { const content = await file.text(); if (current === version.current) setData(content); } catch { if (current === version.current) setError("读取文件失败"); }
      }} /></label>
      <label>或粘贴CSV<textarea required maxLength={250_000} value={data}
        onChange={(e) => { invalidate(); setData(e.target.value); }} /></label>
      <button type="submit" disabled={pending || !data.trim()}>{pending ? "校验中…" : "校验并显示"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <section className="plan-result">
      <strong>用户上传 · 历史数据 · 非实时</strong>
      <p>{result.bar_count}根 · 最后记录：{result.last_observation}</p>
      <p>{result.notice}</p><div className="kline-chart"><Chart bars={result.bars} /></div>
    </section>}
  </section>;
}
