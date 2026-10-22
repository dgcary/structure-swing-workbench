import assert from "node:assert/strict";
import { test } from "node:test";
import { assertTCyclePreview } from "../src/tCyclePreviewContract.ts";

const input = { symbol: "600000", direction: "positive" };
const closed = () => ({
  schema_version: "m8.t_cycle_preview.v1",
  symbol: "600000", direction: "positive", cycle_status: "closed",
  remaining_quantity: "0", realized_gross_pnl: "-200",
  pending_matched_gross_pnl: null,
  notice: "仅为手工数学预览，不授权交易。",
  persisted: false, broker_reconciled: false,
  daily_cycle_limit_verified: false, trade_execution_enabled: false,
});

test("valid complete and partial T calculations preserve negative PnL", () => {
  assert.doesNotThrow(() => assertTCyclePreview(closed(), input));
  assert.doesNotThrow(() => assertTCyclePreview({
    ...closed(), cycle_status: "open", remaining_quantity: "60",
    realized_gross_pnl: null, pending_matched_gross_pnl: "-80",
  }, input));
  assert.doesNotThrow(() => assertTCyclePreview({
    ...closed(), cycle_status: "open", remaining_quantity: "100",
    realized_gross_pnl: null, pending_matched_gross_pnl: "0",
  }, input));
});

test("reject mismatched security, direction, or executable/broker claims", () => {
  for (const change of [
    { symbol: "600001" }, { direction: "reverse" },
    { persisted: true }, { broker_reconciled: true },
    { daily_cycle_limit_verified: true }, { trade_execution_enabled: true },
    { schema_version: "unexpected" }, { notice: "" },
  ]) {
    assert.throws(() => assertTCyclePreview({ ...closed(), ...change }, input),
      /协议异常/);
  }
});

test("reject contradictory closed/open state and malformed displayed amounts", () => {
  for (const change of [
    { cycle_status: "converted" },
    { cycle_status: "closed", remaining_quantity: "10" },
    { cycle_status: "closed", realized_gross_pnl: null },
    { cycle_status: "closed", pending_matched_gross_pnl: "5" },
    { cycle_status: "open", remaining_quantity: "0",
      realized_gross_pnl: null, pending_matched_gross_pnl: "0" },
    { cycle_status: "open", remaining_quantity: "10",
      realized_gross_pnl: "1", pending_matched_gross_pnl: "0" },
    { cycle_status: "open", remaining_quantity: "10",
      realized_gross_pnl: null, pending_matched_gross_pnl: null },
    { remaining_quantity: "Infinity" }, { remaining_quantity: "-1" },
    { realized_gross_pnl: "NaN" }, { realized_gross_pnl: " " },
  ]) {
    assert.throws(() => assertTCyclePreview({ ...closed(), ...change }, input),
      /协议异常/);
  }
});
