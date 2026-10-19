import assert from "node:assert/strict";
import { test } from "node:test";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

const keys = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
];
const metric = (key) => ({
  key, label: key, unit: "", value: null, status: "unavailable",
  source: null, as_of: null,
});
const baseline = () => ({
  schema_version: "m8.overview.v1", mode: "read_only",
  notice: "未接入真实账户，不授权交易。",
  trade_execution_enabled: false,
  metrics: keys.map(metric),
  holdings: null, effective_plans: null, pending_actions: null, audit_results: null,
});
const snapshot = () => ({
  ...baseline(),
  schema_version: "m8.account_snapshot_preview.v1",
  mode: "isolated_csv_preview", input_source: "user_uploaded_csv",
  persisted: false, realtime: false, full_account_verified: false,
  imported_kinds: ["account"],
});

test("valid missing-data overview and isolated CSV preview remain display-only", () => {
  assert.doesNotThrow(() => assertReadOnlyOverview(baseline(), "read_only"));
  assert.doesNotThrow(() => assertReadOnlyOverview(snapshot(), "isolated_csv_preview"));
});

test("a verified metric must have a traceable source and observation time", () => {
  const data = baseline();
  data.metrics[0] = {
    ...data.metrics[0], status: "available", value: "200000",
    source: "CSV/upload", as_of: "2026-10-19T09:30:00+08:00",
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(data, "read_only"));
  for (const invalid of [
    { ...data.metrics[0], source: null },
    { ...data.metrics[0], as_of: null },
    { ...data.metrics[0], value: null },
  ]) {
    const broken = baseline();
    broken.metrics[0] = invalid;
    assert.throws(() => assertReadOnlyOverview(broken, "read_only"), /协议异常/);
  }
});

test("unexpected execution flag, incomplete metrics and invalid holdings fail closed", () => {
  for (const change of [
    { trade_execution_enabled: true },
    { metrics: keys.slice(1).map(metric) },
    { metrics: [...keys.slice(1), keys[1]].map(metric) },
    { holdings: [{ symbol: "600000", status: "snapshot", quantity: null,
      broker_display_cost: null, core_quantity: null, t_quantity: null,
      source: null, as_of: null, warning: "待核对" }] },
    { audit_results: [] },
  ]) {
    assert.throws(() => assertReadOnlyOverview({ ...baseline(), ...change }, "read_only"),
      /协议异常/);
  }
});

test("CSV preview must never claim live, persistent, verified or executable status", () => {
  for (const change of [
    { persisted: true }, { realtime: true }, { full_account_verified: true },
    { trade_execution_enabled: true }, { imported_kinds: [] },
    { imported_kinds: ["account", "account"] },
    { imported_kinds: ["unsupported"] }, { input_source: "broker_live" },
  ]) {
    assert.throws(() => assertReadOnlyOverview({ ...snapshot(), ...change },
      "isolated_csv_preview"), /协议异常/);
  }
});
