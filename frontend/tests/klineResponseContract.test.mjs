import assert from "node:assert/strict";
import { test } from "node:test";
import { assertHistoricalKlinePreview } from "../src/klineResponseContract.ts";

function preview() {
  return {
    schema_version: "m8.kline_preview.v1",
    source: "user_uploaded_csv",
    timeframe: "day",
    last_observation: "2026-10-20",
    bars: [{ time: "2026-10-20", open: "10", high: "11",
      low: "9", close: "10.5", volume: "1000" }],
    bar_count: 1,
    persisted: false,
    realtime: false,
    setup_detected: false,
    trade_execution_enabled: false,
    notice: "仅用户上传历史数据，不授权交易。",
  };
}

test("valid uploaded historical K-line preview is display-only", () => {
  assert.doesNotThrow(() => assertHistoricalKlinePreview(preview(), "day"));
});

test("missing or enabled safety flags fail closed", () => {
  for (const key of ["persisted", "realtime", "setup_detected", "trade_execution_enabled"]) {
    const absent = preview();
    delete absent[key];
    assert.throws(() => assertHistoricalKlinePreview(absent, "day"), /协议异常/,
      key + " absent must not be interpreted as false");
    const enabled = { ...preview(), [key]: true };
    assert.throws(() => assertHistoricalKlinePreview(enabled, "day"), /协议异常/,
      key + " true must not be displayed");
  }
});

test("historical preview requires consistent provenance, timeframe and count", () => {
  for (const change of [
    { schema_version: "unknown" }, { source: "live_broker" },
    { timeframe: "5m" }, { last_observation: "2026-10-19" },
    { bar_count: 2 }, { notice: "" }, { bars: [] },
    { bars: [{ ...preview().bars[0], close: "Infinity" }] },
  ]) {
    assert.throws(() => assertHistoricalKlinePreview(
      { ...preview(), ...change }, "day"), /协议异常/);
  }
});
