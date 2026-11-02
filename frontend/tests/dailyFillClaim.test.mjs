import assert from "node:assert/strict";
import { test } from "node:test";
import { buildDailyFillClaim, parseDailyCoverage } from "../src/dailyFillClaim.ts";

const input = {
  enabled: true,
  marketDate: "2026-10-16",
  exportedAt: "2026-10-16T16:00:00+08:00",
  completeThrough: "2026-10-16T15:30:00+08:00",
  exportReference: "本地导出 01",
  fillIds: "A01\nA02",
  declaredFullDay: true,
};

test("optional self-reported daily claim stays separate from plain CSV preview", () => {
  assert.equal(buildDailyFillClaim({ ...input, enabled: false }, true), null);
  assert.deepEqual(buildDailyFillClaim(input, true), {
    market_date: "2026-10-16",
    exported_at: input.exportedAt,
    complete_through: input.completeThrough,
    export_reference: input.exportReference,
    expected_fill_ids: ["A01", "A02"],
    declared_full_day: true,
  });
});

test("self-reported claim requires fill CSV and valid, ordered source times", () => {
  assert.throws(() => buildDailyFillClaim(input, false), /成交 CSV/);
  assert.throws(() => buildDailyFillClaim({ ...input, marketDate: "2026-02-30" }, true), /交易日/);
  assert.throws(() => buildDailyFillClaim({ ...input, exportedAt: "2026-10-16T16:00:00" }, true), /时区/);
  assert.throws(() => buildDailyFillClaim({ ...input, completeThrough: "2026-10-16T17:00:00+08:00" }, true), /水位/);
});

test("self-reported fill IDs cannot be empty, duplicated or oversized", () => {
  assert.throws(() => buildDailyFillClaim({ ...input, fillIds: "" }, true), /成交编号/);
  assert.throws(() => buildDailyFillClaim({ ...input, fillIds: "A01\nA01" }, true), /重复/);
  assert.throws(() => buildDailyFillClaim({ ...input, fillIds: "A01\n" }, true), /空行/);
  assert.throws(() => buildDailyFillClaim({ ...input, fillIds: "x".repeat(129) }, true), /长度/);
});

const coverage = {
  status: "matched_unverified",
  market_date: "2026-10-16",
  recorded_fill_count: 2,
  declared_fill_count: 2,
  missing_fill_count: 0,
  unexpected_fill_count: 0,
  detail_mismatch_fill_ids: null,
  duplicate_csv_rows: 0,
  outside_watermark_fill_count: 0,
  outside_claimed_day_fill_count: 0,
  broker_reconciled: false,
  trade_execution_enabled: false,
  warning: "仅与用户自报清单一致。",
};

test("coverage contract preserves unverified status and fails closed on certification", () => {
  assert.equal(parseDailyCoverage(coverage, true)?.status, "matched_unverified");
  assert.equal(parseDailyCoverage(null, false), null);
  assert.throws(() => parseDailyCoverage(coverage, false), /协议/);
  assert.throws(() => parseDailyCoverage(null, true), /对照结果/);
  assert.throws(() => parseDailyCoverage({ ...coverage, broker_reconciled: true }, true), /协议/);
  assert.throws(() => parseDailyCoverage({ ...coverage, status: "verified" }, true), /协议/);
  assert.throws(() => parseDailyCoverage({ ...coverage, missing_fill_count: -1 }, true), /协议/);
});
