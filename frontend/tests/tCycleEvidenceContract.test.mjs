import assert from "node:assert/strict";
import { test } from "node:test";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

const keys = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
];
const overview = (cycles) => ({
  schema_version: "m8.overview.v1",
  mode: "read_only",
  notice: "只读成交证据，未核验券商全量",
  trade_execution_enabled: false,
  metrics: keys.map((key) => ({
    key, label: key, unit: "", status: "unavailable",
    value: null, source: null, as_of: null,
  })),
  holdings: null,
  effective_plans: [],
  pending_actions: [],
  audit_results: [],
  t_cycle_evidence: cycles,
});
const closed = {
  symbol: "600000",
  cycle_key: "t-001",
  plan_version_id: "version-1",
  market_date: "2026-10-27",
  direction: "positive",
  state: "closed",
  opening_quantity: "100",
  closing_quantity: "100.0000",
  end_of_day_unclosed: false,
  residual_quantity: null,
  ordinary_effect: null,
  requires_reaudit: false,
  as_of: "2026-10-27T14:30:00+08:00",
  sources: ["成交记录/fill-1/manual", "成交记录/fill-2/manual"],
  broker_reconciled: false,
  trade_execution_enabled: false,
  warning: "只证明已记录的单周期配对，未核验券商全量成交",
};

test("recorded paired legs are display-only; daily verified count stays unavailable", () => {
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([closed]), "read_only"));
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([]), "read_only"));
  assert.doesNotThrow(() => assertReadOnlyOverview(overview(null), "read_only"));
});

test("end-of-day residual is displayed only as an unverified ordinary adjustment", () => {
  const open = {
    ...closed, state: "open", direction: "reverse",
    opening_quantity: "100.00", closing_quantity: "40",
    end_of_day_unclosed: true, residual_quantity: "60",
    ordinary_effect: "普通加仓待核验", requires_reaudit: true,
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([open]), "read_only"));
  for (const broken of [
    { ...open, residual_quantity: "61" },
    { ...open, ordinary_effect: "普通减仓待核验" },
    { ...open, requires_reaudit: false },
    { ...open, end_of_day_unclosed: false },
    { ...open, state: "closed" },
  ]) {
    assert.throws(() => assertReadOnlyOverview(overview([broken]), "read_only"), /协议异常/);
  }
});

test("conflicting T evidence cannot be presented as a verified cycle or executable order", () => {
  const conflict = {
    ...closed, cycle_key: null, direction: null, state: "conflict",
    opening_quantity: null, closing_quantity: null, as_of: null,
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([conflict]), "read_only"));
  for (const broken of [
    { ...closed, broker_reconciled: true },
    { ...closed, trade_execution_enabled: true },
    { ...closed, state: "closed", closing_quantity: "99.9999" },
    { ...closed, state: "open", closing_quantity: "100" },
    { ...closed, sources: [] },
    { ...closed, market_date: "2026-02-30" },
    { ...conflict, opening_quantity: "100" },
    { ...closed, as_of: "未来时间" },
  ]) {
    assert.throws(() => assertReadOnlyOverview(overview([broken]), "read_only"), /协议异常/);
  }
});

test("temporary CSV preview cannot borrow persisted T-cycle evidence", () => {
  const csv = {
    ...overview([closed]), schema_version: "m8.account_snapshot_preview.v1",
    mode: "isolated_csv_preview", input_source: "user_uploaded_csv",
    imported_kinds: ["account"], persisted: false, realtime: false,
    full_account_verified: false,
    effective_plans: null, pending_actions: null, audit_results: null,
  };
  assert.throws(() => assertReadOnlyOverview(csv, "isolated_csv_preview"), /协议异常/);
  assert.doesNotThrow(() => assertReadOnlyOverview({
    ...csv, t_cycle_evidence: null,
  }, "isolated_csv_preview"));
});
