import assert from "node:assert/strict";
import test from "node:test";
import { buildSellAllocations } from "../src/manualSellAllocation.ts";

const lots = [
  { symbol: "600000.SH", quantity: "50" },
  { symbol: "000001.SZ", quantity: "10" },
  { symbol: "600000.SH", quantity: "40" },
];

test("one sale allocates its full quantity across two buy lots", () => {
  assert.deepEqual(buildSellAllocations(lots, "600000.SH", "70", { 0: "30", 2: "40" }), [
    { lot_index: 0, quantity: "30" }, { lot_index: 2, quantity: "40" },
  ]);
});

test("one matching lot can take the entire sale automatically", () => {
  assert.deepEqual(buildSellAllocations(lots, "000001.SZ", "10", {}), [
    { lot_index: 1, quantity: "10" },
  ]);
});

test("allocation must match total and cannot oversell a lot", () => {
  assert.throws(() => buildSellAllocations(lots, "600000.SH", "70", { 0: "30" }));
  assert.throws(() => buildSellAllocations(lots, "600000.SH", "70", { 0: "50", 2: "50" }));
  assert.throws(() => buildSellAllocations(lots, "600000.SH", "70", { 0: "30.00001", 2: "40" }));
});
