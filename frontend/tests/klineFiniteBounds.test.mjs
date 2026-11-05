import assert from "node:assert/strict";
import { test } from "node:test";
import { validBars } from "../src/klinePreviewContract.ts";

function candle(price) {
  return { time: "2026-10-20", open: price, high: price, low: price, close: price, volume: "100" };
}

test("reject K-line values too large for finite SVG bounds", () => {
  assert.equal(validBars([candle("1.7976931348623157e308")], "day"), false);
});

test("reject K-line values too small for finite SVG padding", () => {
  assert.equal(validBars([candle("5e-324")], "day"), false);
});
