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
  market_calendar_status: "session",
  direction: "positive",
  state: "closed",
  opening_quantity: "100",
  closing_quantity: "100.0000",
  end_of_day_unclosed: false,
  residual_quantity: null,
  ordinary_effect: null,
  requires_reaudit: false,
  recorded_daily_limit_alert: null,
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


test("daily T limit warning is mandatory for three recorded closed pairs", () => {
  const rows = ["a", "b", "c"].map((key) => ({
    ...closed, cycle_key: key,
    sources: ["成交记录/" + key + "-open/manual", "成交记录/" + key + "-close/manual"],
    recorded_daily_limit_alert: true,
    warning: "已记录至少3个完整配对，疑似超限；未核验券商全量成交",
  }));
  assert.doesNotThrow(() => assertReadOnlyOverview(overview(rows), "read_only"));
  assert.throws(() => assertReadOnlyOverview(
    overview(rows.map((row, index) => ({
      ...row, recorded_daily_limit_alert: index === 2 ? null : true,
    }))), "read_only",
  ), /协议异常/);
  assert.throws(() => assertReadOnlyOverview(
    overview([closed, { ...closed, cycle_key: "b", recorded_daily_limit_alert: true }]),
    "read_only",
  ), /协议异常/);
  assert.throws(() => assertReadOnlyOverview(
    overview([{ ...closed, recorded_daily_limit_alert: false }]), "read_only",
  ), /协议异常/);
  assert.doesNotThrow(() => assertReadOnlyOverview(
    overview(rows.map((row, index) => ({
      ...row, symbol: index === 2 ? "000001" : "600000",
      recorded_daily_limit_alert: null,
    }))), "read_only",
  ));
});

test("a closed T pair requires a keyed session, matching market date and source time", () => {
  const conflict = {
    ...closed, state: "conflict", cycle_key: null, direction: null,
    opening_quantity: null, closing_quantity: null, as_of: null,
    market_calendar_status: "closed",
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([conflict]), "read_only"));
  for (const broken of [
    { ...closed, market_calendar_status: "closed" },
    { ...closed, market_calendar_status: "unknown" },
    { ...closed, market_calendar_status: undefined },
    { ...closed, cycle_key: null },
    { ...closed, cycle_key: " " },
    { ...closed, plan_version_id: null },
    { ...closed, plan_version_id: " " },
    { ...closed, as_of: "2026-10-28T00:01:00+08:00" },
    { ...closed, market_date: "2026-10-26" },
  ]) {
    assert.throws(() => assertReadOnlyOverview(overview([broken]), "read_only"), /协议异常/);
  }
});

test("repeated T identity and reused fill sources cannot inflate recorded cycle counts", () => {
  const second = {
    ...closed, cycle_key: "t-002",
    sources: ["成交记录/fill-3/manual", "成交记录/fill-4/manual"],
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([closed, second]), "read_only"));
  for (const broken of [
    [closed, { ...closed }],
    [closed, { ...second, sources: ["成交记录/fill-1/manual", "成交记录/fill-4/manual"] }],
    [{ ...closed, sources: ["成交记录/fill-1/manual", "成交记录/fill-1/manual"] }],
  ]) {
    assert.throws(() => assertReadOnlyOverview(overview(broken), "read_only"), /协议异常/);
  }
});


test("recorded T pair must have distinct evidence for both legs", () => {
  // A single execution cannot certify both a sale and a buyback.
  const singleSource = ["成交记录/one-fill/manual"];
  for (const broken of [
    { ...closed, sources: singleSource },
    {
      ...closed, state: "open", opening_quantity: "100",
      closing_quantity: "40", sources: singleSource,
    },
  ]) {
    assert.throws(() => assertReadOnlyOverview(overview([broken]), "read_only"), /协议异常/);
  }
  // One opening fill is sufficient to display an unclosed cycle, but not
  // to certify a completed buy/sell pairing or authorize a trade.
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([{
    ...closed, state: "open", closing_quantity: "0", sources: singleSource,
  }]), "read_only"));
});

test("recorded T fills require a complete ID/source and one unique fill ID", () => {
  const second = {
    ...closed, cycle_key: "t-002",
    sources: ["成交记录/fill-3/manual", "成交记录/fill-4/manual"],
  };
  assert.doesNotThrow(() => assertReadOnlyOverview(overview([closed, second]), "read_only"));

  // Two labels do not make the same persisted fill two independent executions.
  for (const broken of [
    [{ ...closed, sources: ["成交记录/same/manual", "成交记录/same/import"] }],
    [closed, { ...second, sources: ["成交记录/fill-1/import", "成交记录/fill-4/manual"] }],
    [{ ...closed, sources: ["成交记录//manual", "成交记录/fill-2/manual"] }],
    [{ ...closed, sources: ["成交记录/fill-1/", "成交记录/fill-2/manual"] }],
    [{ ...closed, sources: ["成交记录/ /manual", "成交记录/fill-2/manual"] }],
    [{ ...closed, sources: ["成交记录/fill-1/ ", "成交记录/fill-2/manual"] }],
  ]) {
    assert.throws(() => assertReadOnlyOverview(overview(broken), "read_only"), /协议异常/);
  }
});
