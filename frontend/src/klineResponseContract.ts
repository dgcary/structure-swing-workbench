import { validBars, type Candle } from "./klinePreviewContract.ts";

export type HistoricalKlinePreview = {
  schema_version: "m8.kline_preview.v1";
  source: "user_uploaded_csv";
  timeframe: "day" | "5m" | "15m";
  last_observation: string;
  bars: Candle[];
  bar_count: number;
  persisted: false;
  realtime: false;
  setup_detected: false;
  trade_execution_enabled: false;
  notice: string;
};

export function assertHistoricalKlinePreview(
  payload: unknown,
  timeframe: "day" | "5m" | "15m",
): asserts payload is HistoricalKlinePreview {
  const invalid = (): never => {
    throw new Error("K线数据协议异常或超出浏览器可绘制范围");
  };
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) invalid();
  const value = payload as Record<string, unknown>;
  if (value.schema_version !== "m8.kline_preview.v1" ||
      value.source !== "user_uploaded_csv" ||
      value.timeframe !== timeframe ||
      value.persisted !== false || value.realtime !== false ||
      value.setup_detected !== false || value.trade_execution_enabled !== false ||
      !Array.isArray(value.bars) || !validBars(value.bars, timeframe) ||
      !Number.isSafeInteger(value.bar_count) || value.bar_count !== value.bars.length ||
      value.last_observation !== value.bars[value.bars.length - 1].time ||
      typeof value.notice !== "string" || !value.notice.trim()) invalid();
}
