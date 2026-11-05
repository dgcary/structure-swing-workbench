import assert from "node:assert/strict";
import { test } from "node:test";
import { validBars } from "../src/klinePreviewContract.ts";

const candle = { time: "2026-10-20T09:35:00+08:00", open: "10", high: "11", low: "9", close: "10", volume: "100" };

test("unsupported K-line timeframe is never treated as a minute series", () => {
  assert.equal(validBars([candle], "invalid"), false);
});
