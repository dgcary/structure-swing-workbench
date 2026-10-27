import assert from "node:assert/strict";
import { test } from "node:test";
import { assertReadOnlyOverview } from "../src/overviewContract.ts";

const keys = [
  "equity", "available_cash", "position_ratio", "position_count",
  "account_risk", "t_cycles_today", "open_t_cycles",
  "rotation_status", "highest_audit",
];
const baseline = () => ({
  schema_version: "m8.overview.v1", mode: "read_only",
  notice: "只读历史记录，不授权交易", trade_execution_enabled: false,
  metrics: keys.map((key) => ({
    key, label: key, unit: "", status: "unavailable",
    value: null, source: null, as_of: null,
  })),
  holdings: null, effective_plans: [], pending_actions: [], audit_results: [],
});
const plan = {
  id: "plan-v1", symbol: "600000", name: "人工计划", version: 1,
  state_zh: "生效", invalidation_price: "10.00", first_target_price: "13.00",
  initial_risk: null, current_risk: null,
  source: "正式计划版本/plan-v1", as_of: null, warning: "历史计划，未核实",
};
const action = {
  id: "action-1", symbol: "600000", action_zh: "初始建仓", status_zh: "已审计",
  planned_price_low: "11", planned_price_high: "11.5",
  planned_for_date: null, date_status: "unverified",
  source: "正式交易动作/action-1", as_of: null,
  executable: false, warning: "不得据此执行",
};
const audit = {
  id: "audit-1", level: "hard_fail", level_zh: "硬性失败",
  summary: "结构已失效", source: "审计记录/audit-1/m2",
  as_of: null, executable: false, warning: "仅历史审计",
};

test("persisted formal plans, actions and audits are accepted only as read-only", () => {
  const data = baseline();
  data.effective_plans = [plan];
  data.pending_actions = [action];
  data.audit_results = [audit];
  assert.doesNotThrow(() => assertReadOnlyOverview(data, "read_only"));
});

test("persisted rows reject missing provenance, invalid symbols and execution flags", () => {
  const data = baseline();
  data.effective_plans = [plan];
  data.pending_actions = [action];
  data.audit_results = [audit];
  for (const [key, broken] of [
    ["effective_plans", { ...plan, source: "本机草稿/plan-v1" }],
    ["effective_plans", { ...plan, symbol: "unknown" }],
    ["effective_plans", { ...plan, invalidation_price: "NaN" }],
    ["pending_actions", { ...action, executable: true }],
    ["pending_actions", { ...action, as_of: "2026-10-20" }],
    ["audit_results", { ...audit, level: "approved" }],
    ["audit_results", { ...audit, executable: true }],
  ]) {
    assert.throws(() => assertReadOnlyOverview({
      ...data, [key]: [broken],
    }, "read_only"), /协议异常/, key);
  }
  assert.throws(() => assertReadOnlyOverview({
    ...data, pending_actions: [action, action],
  }, "read_only"), /协议异常/);
});

test("only explicitly dated sourced actions may be labelled as today's manual plan", () => {
  const data = baseline();
  const sourced = { ...action, as_of: "2026-10-27T10:00:00+08:00",
    planned_for_date: "2026-10-27", date_status: "today" };
  data.pending_actions = [sourced];
  assert.doesNotThrow(() => assertReadOnlyOverview(data, "read_only"));
  for (const broken of [
    { ...sourced, planned_for_date: null },
    { ...sourced, planned_for_date: "2026-02-30" },
    { ...sourced, planned_for_date: "2026-10-27T00:00:00" },
    { ...sourced, as_of: null },
    { ...action, date_status: "today" },
    { ...sourced, date_status: "unknown" },
  ]) {
    assert.throws(() => assertReadOnlyOverview({
      ...data, pending_actions: [broken],
    }, "read_only"), /协议异常/);
  }
});

test("isolated CSV can never carry persisted plans or audits", () => {
  const csv = {
    ...baseline(), schema_version: "m8.account_snapshot_preview.v1",
    mode: "isolated_csv_preview", input_source: "user_uploaded_csv",
    persisted: false, realtime: false, full_account_verified: false,
    imported_kinds: ["account"],
  };
  assert.throws(() => assertReadOnlyOverview(csv, "isolated_csv_preview"), /协议异常/);
  for (const key of ["effective_plans", "pending_actions", "audit_results"]) {
    const safe = { ...csv, effective_plans: null, pending_actions: null, audit_results: null };
    safe[key] = key === "effective_plans" ? [plan] :
      key === "pending_actions" ? [action] : [audit];
    assert.throws(() => assertReadOnlyOverview(safe, "isolated_csv_preview"), /协议异常/);
  }
});
