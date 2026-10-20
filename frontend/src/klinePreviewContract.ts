export function validCandle(open: number, high: number, low: number, close: number): boolean {
  return [open, high, low, close].every((n) => Number.isFinite(n) && n > 0) && high >= Math.max(open, low, close) && low <= Math.min(open, high, close);
}
