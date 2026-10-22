import assert from "node:assert/strict";
import { test } from "node:test";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

const keys = ["equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles", "rotation_status", "highest_audit"];
const base = () => ({
  schema_version: "m8.overview.v1", mode: "read_only", notice: "只读来源，不授权交易",
  trade_execution_enabled: false,
  metrics: keys.map((key) => ({ key, label: key, unit: "", value: null,
    status: "unavailable", source: null, as_of: null })),
  holdings: null, effective_plans: null, pending_actions: null, audit_results: null,
});
const holding = () => ({ symbol: "600000", status: "snapshot", quantity: "100",
  broker_display_cost: "10.2", core_quantity: "70", t_quantity: "30",
  source: "CSV", as_of: "2026-10-22T08:00:00+08:00", warning: "仅为来源内快照" });
const metric = (value) => {
  const data = base();
  data.metrics[0] = { ...data.metrics[0], value, status: "available",
    source: "CSV", as_of: "2026-10-22T08:00:00+08:00" };
  return data;
};

test("reject JS hex, binary, octal, whitespace and separators in sourced numbers", () => {
  for (const bad of ["0x10", "0b10", "0o10", " 10", "10 ", "+10", "1_000",
    "1,000", "Infinity", "NaN", ""]) {
    assert.throws(() => assertReadOnlyOverview(metric(bad), "read_only"), /协议异常/, bad);
    for (const field of ["quantity", "broker_display_cost", "core_quantity", "t_quantity"]) {
      const data = base();
      data.holdings = [{ ...holding(), [field]: bad }];
      assert.throws(() => assertReadOnlyOverview(data, "read_only"), /协议异常/,
        field + "=" + bad);
    }
  }
});

test("negative broker cost and signed unanchored delta remain allowed", () => {
  const data = base();
  data.holdings = [{ ...holding(), broker_display_cost: "-0.5" }];
  assert.doesNotThrow(() => assertReadOnlyOverview(data, "read_only"));
  data.holdings = [{ ...holding(), status: "unanchored", quantity: null,
    broker_display_cost: null, core_quantity: null, t_quantity: null,
    unanchored_fill_delta: "-100.25" }];
  assert.doesNotThrow(() => assertReadOnlyOverview(data, "read_only"));
  data.holdings[0].unanchored_fill_delta = "0x10";
  assert.throws(() => assertReadOnlyOverview(data, "read_only"), /协议异常/);
});

test("finite scientific notation from Python Decimal stays valid", () => {
  assert.doesNotThrow(() => assertReadOnlyOverview(metric("1.25E+4"), "read_only"));
  const data = base();
  data.holdings = [{ ...holding(), quantity: "1E+2",
    core_quantity: "7E1", t_quantity: "3E1" }];
  assert.doesNotThrow(() => assertReadOnlyOverview(data, "read_only"));
});
