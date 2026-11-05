import assert from "node:assert/strict";
import test from "node:test";
import { summarizeManualAccount } from "../src/manualOverview.ts";

test("manual account summary keeps unknown values and counts distinct stocks", () => {
  const result = summarizeManualAccount({
    observed_at: "2026-11-05T09:00:00+08:00",
    available_cash: "123.45", total_equity: null,
    lots: [
      { symbol: "002670.SZ", quantity: "100", paid_amount: null, bought_at: null },
      { symbol: "002670.SZ", quantity: "200", paid_amount: null, bought_at: null },
      { symbol: "600000.SH", quantity: "50", paid_amount: null, bought_at: null },
    ],
  });
  assert.equal(result.stockCount, 2);
  assert.equal(result.totalEquity, null);
  assert.equal(result.availableCash, "123.45");
  assert.equal(result.lots.length, 3);
});
