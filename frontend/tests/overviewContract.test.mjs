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
    { ...data.metrics[0], as_of: "invalid-date" },
    { ...data.metrics[0], as_of: "2026-10-19" },
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

test("sourced holdings must have a finite nonnegative quantity and a dated origin", () => {
  const holding = {
    symbol: "600000", status: "snapshot", quantity: "100",
    broker_display_cost: "12.30", core_quantity: null, t_quantity: null,
    source: "CSV/upload", as_of: "2026-10-19T09:30:00+08:00",
    warning: "仅来源范围内的持仓，尚未核验核心仓",
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(
    { ...baseline(), holdings: [holding] }, "read_only",
  ));
  for (const change of [
    { quantity: "NaN" }, { quantity: "Infinity" }, { quantity: "-100" },
    { quantity: "" }, { source: null }, { source: " " },
    { as_of: null }, { as_of: "not-a-date" },
    { as_of: "2026-10-19" }, { as_of: "2026-10-19T09:30:00" },
  ]) {
    assert.throws(() => assertReadOnlyOverview(
      { ...baseline(), holdings: [{ ...holding, ...change }] }, "read_only",
    ), /协议异常/);
  }
});

test("sourced broker cost must be a finite numeric value, including valid negative cost", () => {
  const holding = {
    symbol: "600000", status: "snapshot", quantity: "100",
    broker_display_cost: "-1.20", core_quantity: null, t_quantity: null,
    source: "CSV/upload", as_of: "2026-10-19T09:30:00+08:00",
    warning: "券商显示成本可因已实现收益为负，仍需保留来源",
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(
    { ...baseline(), holdings: [holding] }, "read_only",
  ));
  for (const broker_display_cost of ["NaN", "Infinity", "-Infinity", "", " ", "invalid"]) {
    assert.throws(() => assertReadOnlyOverview(
      { ...baseline(), holdings: [{ ...holding, broker_display_cost }] }, "read_only",
    ), /协议异常/);
  }
});

test("optional core and T quantities reject negative, non-finite and empty values", () => {
  const holding = {
    symbol: "600000", status: "snapshot", quantity: "100",
    broker_display_cost: "-1.20", core_quantity: "70", t_quantity: "30",
    source: "CSV/upload", as_of: "2026-10-19T09:30:00+08:00",
    warning: "仅为有来源的持仓快照，不构成交易指令",
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(
    { ...baseline(), holdings: [holding] }, "read_only",
  ));
  for (const field of ["core_quantity", "t_quantity"]) {
    for (const bad of ["NaN", "Infinity", "-Infinity", "-1", "", " ", "unknown"]) {
      assert.throws(() => assertReadOnlyOverview(
        { ...baseline(), holdings: [{ ...holding, [field]: bad }] }, "read_only",
      ), /协议异常/);
    }
    assert.doesNotThrow(() => assertReadOnlyOverview(
      { ...baseline(), holdings: [{ ...holding, [field]: null }] }, "read_only",
    ));
  }
});

test("unanchored and conflicting holdings require sourced, timezone-aware observations", () => {
  for (const status of ["unanchored", "conflict"]) {
    const holding = {
      symbol: "600000", status, quantity: null,
      broker_display_cost: null, core_quantity: null, t_quantity: null,
      source: "成交记录/broker-csv", as_of: "2026-10-19T09:30:00+08:00",
      warning: "持仓尚未核实",
    };
    assert.doesNotThrow(() => assertReadOnlyOverview(
      { ...baseline(), holdings: [holding] }, "read_only",
    ));
    for (const change of [
      { source: null }, { source: " " }, { as_of: null },
      { as_of: "2026-10-19" }, { as_of: "2026-10-19T09:30:00" },
    ]) {
      assert.throws(() => assertReadOnlyOverview(
        { ...baseline(), holdings: [{ ...holding, ...change }] }, "read_only",
      ), /协议异常/);
    }
  }
});


test("available numeric metrics reject negative, fractional counts and impossible exposure", () => {
  const sourced = (key, value) => ({
    ...metric(key), status: "available", value,
    source: "CSV/upload", as_of: "2026-10-20T09:30:00+08:00",
  });
  for (const [key, value] of [
    ["equity", "-1"], ["available_cash", "-0.01"],
    ["position_ratio", "-1"], ["position_ratio", "100.01"],
    ["account_risk", "-0.1"], ["position_count", "1.5"],
    ["t_cycles_today", "-1"], ["t_cycles_today", "0.5"],
    ["open_t_cycles", "-1"], ["open_t_cycles", "2.2"],
  ]) {
    const broken = baseline();
    broken.metrics[keys.indexOf(key)] = sourced(key, value);
    assert.throws(() => assertReadOnlyOverview(broken, "read_only"),
      /协议异常/, `${key}=${value} must not be presented as verified`);
  }
  const valid = baseline();
  valid.metrics[keys.indexOf("position_count")] = sourced("position_count", "2");
  valid.metrics[keys.indexOf("position_ratio")] = sourced("position_ratio", "100");
  assert.doesNotThrow(() => assertReadOnlyOverview(valid, "read_only"));
});

test("unavailable metric cannot retain a verified source or observation time", () => {
  for (const change of [
    { source: "CSV/upload" }, { as_of: "2026-10-20T09:30:00+08:00" },
  ]) {
    const broken = baseline();
    broken.metrics[0] = { ...broken.metrics[0], ...change };
    assert.throws(() => assertReadOnlyOverview(broken, "read_only"), /协议异常/);
  }
});
