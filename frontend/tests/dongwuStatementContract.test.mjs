import assert from "node:assert/strict";
import test from "node:test";
import {
  canUploadLocalStatement, localStatementEndpoint, parseDongwuStatementCheck,
} from "../src/dongwuStatementContract.ts";

const good = {
  schema_version: "m8.dongwu_statement_check.v1",
  mode: "local_pdf_preview",
  notice: "仅核对所选账单内部一致性；非实时账户、非券商全量认证，不保存或授权交易。",
  status: "matched_unverified",
  period_start: "2026-08-05",
  period_end: "2026-11-02",
  summary_row_count: 48,
  detail_row_count: 52,
  matched_group_count: 48,
  missing_summary_group_count: 0,
  extra_summary_group_count: 0,
  mismatched_group_count: 0,
  repaired_summary_rows: 3,
  broker_reconciled: false,
  full_account_verified: false,
  trade_execution_enabled: false,
  execution_ids_available: false,
  execution_times_available: false,
  footer_totals_checked: true,
  footer_totals_mismatched_count: 0,
};

test("accepts only aggregate, historically scoped PDF evidence", () => {
  assert.equal(parseDongwuStatementCheck(good).status, "matched_unverified");
});

test("rejects broker certification, live data and private row fields", () => {
  for (const changed of [
    { ...good, broker_reconciled: true },
    { ...good, full_account_verified: true },
    { ...good, trade_execution_enabled: true },
    { ...good, execution_ids_available: true },
    { ...good, account_id: "private" },
    { ...good, trades: [] },
  ]) {
    assert.throws(() => parseDongwuStatementCheck(changed));
  }
});

test("rejects impossible dates, missing footer checks and dishonest status", () => {
  for (const changed of [
    { ...good, period_start: "2026-02-30" },
    { ...good, period_end: "2026-08-04" },
    { ...good, footer_totals_checked: false },
    { ...good, footer_totals_mismatched_count: 1 },
    { ...good, matched_group_count: 49 },
    { ...good, summary_row_count: -1 },
  ]) {
    assert.throws(() => parseDongwuStatementCheck(changed));
  }
});

test("accepts an explicit internal mismatch without certifying the account", () => {
  const mismatch = { ...good, status: "mismatch", mismatched_group_count: 1,
    matched_group_count: 47 };
  assert.equal(parseDongwuStatementCheck(mismatch).status, "mismatch");
});

test("a remote Web page cannot send a selected PDF to its server", () => {
  assert.equal(canUploadLocalStatement({ protocol: "http:", hostname: "localhost" }), true);
  assert.equal(canUploadLocalStatement({ protocol: "https:", hostname: "127.0.0.1" }), true);
  assert.equal(canUploadLocalStatement({ protocol: "http:", hostname: "[::1]" }), true);
  assert.equal(canUploadLocalStatement({ protocol: "https:", hostname: "workbench.example" }), false);
  assert.equal(canUploadLocalStatement({ protocol: "http:", hostname: "192.168.1.10" }), false);
  assert.equal(canUploadLocalStatement({ protocol: "file:", hostname: "" }), false);
});

test("PDF destination is a fixed loopback API, never the configurable Web proxy", () => {
  assert.equal(localStatementEndpoint, "http://127.0.0.1:8000/workbench/dongwu-statement-check");
  assert.equal(new URL(localStatementEndpoint).hostname, "127.0.0.1");
});
