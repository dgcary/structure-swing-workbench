import assert from "node:assert/strict";
import { test } from "node:test";
import { validObservedAt } from "../src/validObservedAt.ts";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

const keys = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
];
const baseline = () => ({
  schema_version: "m8.overview.v1",
  mode: "read_only",
  notice: "仅显示来源事实，不授权交易",
  trade_execution_enabled: false,
  metrics: keys.map((key) => ({
    key, label: key, unit: "", value: null, status: "unavailable",
    source: null, as_of: null,
  })),
  holdings: null, effective_plans: null, pending_actions: null, audit_results: null,
});

test("observation timestamp requires real calendar day and timezone", () => {
  for (const value of [
    "2024-02-29T09:30:00+08:00",
    "2000-02-29T09:30:00Z",
    "2026-10-21T09:30:00.123-05:00",
  ]) assert.equal(validObservedAt(value), true, value);
  for (const value of [
    "2026-02-29T09:30:00+08:00",
    "1900-02-29T09:30:00Z",
    "2024-02-30T09:30:00Z",
    "2026-04-31T09:30:00Z",
    "2026-13-01T09:30:00Z",
    "2026-00-01T09:30:00Z",
    "2026-10-00T09:30:00Z",
    "2026-10-32T09:30:00Z",
    "2026-10-21T24:00:00Z",
    "2026-10-21T09:60:00Z",
    "2026-10-21T09:30:60Z",
    "2026-10-21T09:30:00+24:00",
    "2026-10-21T09:30:00+08:60",
    "2026-10-21T09:30:00",
    "2026-10-21",
    null,
  ]) assert.equal(validObservedAt(value), false, String(value));
});

test("overview metric and holding observations fail closed on impossible dates", () => {
  const impossible = "2026-02-30T09:30:00+08:00";
  const metric = baseline();
  metric.metrics[0] = {
    ...metric.metrics[0], status: "available", value: "1000",
    source: "CSV", as_of: impossible,
  };
  assert.throws(() => assertReadOnlyOverview(metric, "read_only"), /协议异常/);

  const holding = baseline();
  holding.holdings = [{
    symbol: "600000", status: "snapshot", quantity: "100",
    broker_display_cost: "12.30", core_quantity: null, t_quantity: null,
    source: "CSV", as_of: impossible, warning: "来源时间不可信",
  }];
  assert.throws(() => assertReadOnlyOverview(holding, "read_only"), /协议异常/);
});
