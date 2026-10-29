import assert from "node:assert/strict";
import { test } from "node:test";
import { assertTCyclePreview } from "../src/tCyclePreviewContract.ts";

const input = { symbol: "600000", direction: "positive" };
const closed = () => ({
  schema_version: "m8.t_cycle_preview.v1",
  symbol: "600000", direction: "positive", cycle_status: "closed",
  remaining_quantity: "0", realized_gross_pnl: "-200",
  pending_matched_gross_pnl: null,
  projected_risk: null,
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

test("manual reverse-T risk requires unverified provenance and correct tier", () => {
  const risk = {
    projected_max_loss: "400", projected_account_risk_pct: "1.6",
    account_total_max_loss: "500", account_total_risk_pct: "2",
    other_positions_max_loss: "100", existing_t_max_loss: "0",
    core_max_loss: "350", new_t_max_loss: "50",
    level: "PASS", verified: false, source: "用户手工假设",
    warning: "未核验账户及T+1，不授权交易。",
  };
  const reverse = { ...closed(), direction: "reverse", projected_risk: risk };
  const reverseInput = { symbol: "600000", direction: "reverse", expectRisk: true };
  assert.doesNotThrow(() => assertTCyclePreview(reverse, reverseInput));
  for (const change of [
    { verified: true }, { level: "WARNING" }, { source: "" },
    { warning: "" }, { projected_account_risk_pct: "NaN" },
    { projected_max_loss: "-1" }, { new_t_max_loss: "Infinity" },
    { account_total_max_loss: "400" }, { account_total_risk_pct: "3" },
    { other_positions_max_loss: "0" }, { existing_t_max_loss: "10" },
  ]) {
    assert.throws(() => assertTCyclePreview({
      ...reverse, projected_risk: { ...risk, ...change },
    }, reverseInput), /协议异常/);
  }
  assert.throws(() => assertTCyclePreview(reverse, input), /协议异常/);
  assert.throws(() => assertTCyclePreview({ ...reverse, projected_risk: null },
    reverseInput), /协议异常/);
});

test("cross-stock total above 3% does not create a hard fail for one plan", () => {
  const crossStock = {
    ...closed(), direction: "reverse",
    projected_risk: {
      projected_max_loss: "1100", projected_account_risk_pct: "1.1",
      account_total_max_loss: "3600", account_total_risk_pct: "3.6",
      other_positions_max_loss: "2500", existing_t_max_loss: "0",
      core_max_loss: "1000", new_t_max_loss: "100",
      level: "PASS", verified: false, source: "用户手工假设",
      warning: "跨票合计仅展示，不参与单笔审计分级。",
    },
  };
  const reverseInput = { symbol: "600000", direction: "reverse", expectRisk: true };
  assert.doesNotThrow(() => assertTCyclePreview(crossStock, reverseInput));
  assert.throws(() => assertTCyclePreview({
    ...crossStock, projected_risk: { ...crossStock.projected_risk, level: "HARD_FAIL" },
  }, reverseInput), /协议异常/);
  assert.doesNotThrow(() => assertTCyclePreview({
    ...crossStock, projected_risk: {
      ...crossStock.projected_risk,
      projected_max_loss: "3100", projected_account_risk_pct: "3.1",
      account_total_max_loss: "5600", account_total_risk_pct: "5.6",
      core_max_loss: "3000", level: "HARD_FAIL",
    },
  }, reverseInput));
});
