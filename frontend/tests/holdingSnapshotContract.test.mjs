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
