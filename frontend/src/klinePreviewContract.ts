export type Candle = { time: string; open: string; high: string; low: string; close: string; volume: string };
export function validCandle(open: number, high: number, low: number, close: number): boolean {
  return [open, high, low, close].every((n) => Number.isFinite(n) && n > 0) &&
    high >= Math.max(open, low, close) && low <= Math.min(open, high, close);
}
export function validBars(bars: Candle[], timeframe: string): boolean {
  if (!Array.isArray(bars) || !bars.length || bars.length > 500) return false;
  if (!["day", "5m", "15m"].includes(timeframe)) return false;
  let last = -Infinity;
  for (const b of bars) {
    if (!b || typeof b.time !== "string") return false;
    const day = /^\d{4}-\d{2}-\d{2}$/.test(b.time);
    const minute = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(b.time);
    if (timeframe === "day" ? !day : !minute) return false;
    const calendar = b.time.slice(0, 10);
    const calendarInstant = Date.parse(calendar + "T00:00:00Z");
    if (!Number.isFinite(calendarInstant) ||
        new Date(calendarInstant).toISOString().slice(0, 10) !== calendar) return false;
    const t = Date.parse(day ? b.time + "T00:00:00Z" : b.time);
    if (!Number.isFinite(t) || t <= last || (day &&
      new Date(t).toISOString().slice(0, 10) !== b.time)) return false;
    last = t;
    const raw = [b.open, b.high, b.low, b.close, b.volume];
    if (raw.some((v) => typeof v !== "string" || !v.trim())) return false;
    const [o, h, l, c, v] = raw.map(Number);
    if (!validCandle(o, h, l, c) || !Number.isFinite(v) || v < 0) return false;
  }
  const recent = bars.slice(-100);
  const highest = Math.max(...recent.map((bar) => Number(bar.high)));
  const lowest = Math.min(...recent.map((bar) => Number(bar.low)));
  const padding = Math.max((highest - lowest) * 0.05, highest * 0.005);
  const span = highest - lowest + 2 * padding;
  if (!Number.isFinite(highest + padding) || !Number.isFinite(span) || span <= 0) return false;
  return true;
}
