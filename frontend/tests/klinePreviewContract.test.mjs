import assert from "node:assert/strict";
import { test } from "node:test";
import { validBars } from "../src/klinePreviewContract.ts";

const candle = (time, change = {}) => ({
  time, open: "10", high: "12", low: "9", close: "11", volume: "100", ...change,
});

test("chronological timezone-aware candles are accepted", () => {
  assert.equal(validBars([candle("2026-10-19"), candle("2026-10-20")], "day"), true);
  assert.equal(validBars([candle("2026-10-19T09:30:00+08:00"),
    candle("2026-10-19T01:35:00Z")], "5m"), true);
});

test("duplicate or unzoned observations are rejected", () => {
  assert.equal(validBars([candle("2026-10-19"), candle("2026-10-19")], "day"), false);
  assert.equal(validBars([candle("2026-02-30")], "day"), false);
  assert.equal(validBars([candle("2026-02-30T09:30:00+08:00")], "5m"), false);
  assert.equal(validBars([candle("2026-10-19T09:30:00")], "5m"), false);
  assert.equal(validBars([candle("2026-10-19T09:30:00+08:00"),
    candle("2026-10-19T01:30:00Z")], "5m"), false);
});

test("impossible prices, negative volume and oversized data are rejected", () => {
  for (const change of [
    { high: "10.5" }, { low: "11.5" }, { open: "0" },
    { volume: "-1" }, { volume: "NaN" }, { close: "" },
  ]) assert.equal(validBars([candle("2026-10-19", change)], "day"), false);
  assert.equal(validBars([], "day"), false);
  assert.equal(validBars(Array(501).fill(candle("2026-10-19")), "day"), false);
});
