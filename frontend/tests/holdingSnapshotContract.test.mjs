import assert from "node:assert/strict";
import { test } from "node:test";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

test("rejects absent overview provenance", () => {
  assert.throws(() => assertReadOnlyOverview(null, "read_only"), /协议异常/);
  assert.throws(() => assertReadOnlyOverview({}, "read_only"), /协议异常/);
});

const metricKeys = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
];
const metric = (key) => ({
  key, label: key, unit: "", value: null, status: "unavailable",
  source: null, as_of: null,
});
const baseline = (holding) => ({
  schema_version: "m8.overview.v1", mode: "read_only",
  notice: "未接入实时账户", trade_execution_enabled: false,
  metrics: metricKeys.map(metric), holdings: [holding],
  effective_plans: null, pending_actions: null, audit_results: null,
});

const holding = {
  symbol: "600000", status: "snapshot", quantity: "100",
  broker_display_cost: "12.30", core_quantity: null, t_quantity: null,
  source: "CSV/upload", as_of: "2026-10-19T09:30:00+08:00",
  warning: "券商成本有来源，核心仓未核实",
};
const check = (value) => assertReadOnlyOverview(baseline(value), "read_only");

test("sourced snapshot requires a broker display cost", () => {
  assert.doesNotThrow(() => check(holding));
  assert.throws(() => check({ ...holding, broker_display_cost: null }), /协议异常/);
});
