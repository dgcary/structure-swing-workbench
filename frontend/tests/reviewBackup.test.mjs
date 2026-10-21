import assert from "node:assert/strict";
import { test } from "node:test";
import { serializeReviewBackup, restoreReviewBackup } from "../src/reviewBackup.ts";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";
import { REVIEW_KEY, readReviews, saveReview } from "../src/reviewStore.ts";

const input = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "" };
function store() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); },
  };
}
function withPlan(storage) {
  saveDraft(storage, input, null, () => "plan-1");
}
function withReview(storage) {
  withPlan(storage);
  saveReview(storage, { id: "plan-1", version: 1, symbol: "600000" },
    "人工观察", "复盘结论", () => "review-1");
}

test("manual review backup roundtrip requires the referenced plan and never overwrites", () => {
  const source = store();
  withReview(source);
  const backup = serializeReviewBackup(source, () => "2026-10-19T07:00:00+08:00");
  const target = store();
  withPlan(target);
  const restored = restoreReviewBackup(target, backup);
  assert.equal(restored.length, 1);
  assert.deepEqual(readReviews(target), readReviews(source));
  assert.equal(JSON.parse(backup).verified_fills, false);
  const before = target.getItem(REVIEW_KEY);
  assert.throws(() => restoreReviewBackup(target, backup), /禁止导入覆盖/);
  assert.equal(target.getItem(REVIEW_KEY), before);
});

test("review restore refuses orphaned plans and mismatched symbols without writing", () => {
  const source = store();
  withReview(source);
  const backup = serializeReviewBackup(source);
  const noPlans = store();
  assert.throws(() => restoreReviewBackup(noPlans, backup), /请先恢复/);
  assert.equal(noPlans.getItem(REVIEW_KEY), null);
  const wrongPlan = store();
  saveDraft(wrongPlan, { ...input, symbol: "000001" }, null, () => "plan-1");
  assert.throws(() => restoreReviewBackup(wrongPlan, backup), /证券不匹配/);
  assert.equal(wrongPlan.getItem(REVIEW_KEY), null);
});

test("invalid review backups fail closed and preserve existing draft data", () => {
  const source = store();
  withReview(source);
  const valid = JSON.parse(serializeReviewBackup(source));
  const target = store();
  withPlan(target);
  const originalDrafts = target.getItem(DRAFT_KEY);
  const variants = [
    "{}",
    "not-json",
    JSON.stringify({ ...valid, verified_fills: true }),
    JSON.stringify({ ...valid, source: "broker_live" }),
    JSON.stringify({ ...valid, exported_at: "yesterday" }),
    JSON.stringify({ ...valid, records: [] }),
    JSON.stringify({ ...valid, records: [valid.records[0], valid.records[0]] }),
    JSON.stringify({ ...valid, records: [{ ...valid.records[0], lesson: "" }] }),
    "x".repeat(1_000_001),
  ];
  for (const raw of variants) {
    assert.throws(() => restoreReviewBackup(target, raw));
    assert.equal(target.getItem(REVIEW_KEY), null);
    assert.equal(target.getItem(DRAFT_KEY), originalDrafts);
  }
});

test("review export rejects corrupt storage and invalid export timestamps", () => {
  const source = store();
  withReview(source);
  const before = source.getItem(REVIEW_KEY);
  assert.throws(() => serializeReviewBackup(source, () => "not-a-time"), /时间无效/);
  assert.equal(source.getItem(REVIEW_KEY), before);
  source.setItem(REVIEW_KEY, "invalid");
  assert.throws(() => serializeReviewBackup(source));
  assert.equal(source.getItem(REVIEW_KEY), "invalid");
});

test("intervening cross-tab write during restore cannot be overwritten", () => {
  const source = store();
  withReview(source);
  const backup = serializeReviewBackup(source);
  const target = store();
  withPlan(target);
  let reads = 0;
  const guarded = {
    getItem: (key) => {
      if (key === REVIEW_KEY && ++reads === 2) {
        target.setItem(REVIEW_KEY, "new-tab-data");
      }
      return target.getItem(key);
    },
    setItem: (key, value) => target.setItem(key, value),
  };
  assert.throws(() => restoreReviewBackup(guarded, backup), /导入期间/);
  assert.equal(target.getItem(REVIEW_KEY), "new-tab-data");
});

test("review restore refuses a concurrent plan change before committing reviews", () => {
  const source = store();
  withReview(source);
  const backup = serializeReviewBackup(source);
  const target = store();
  withPlan(target);
  let draftReads = 0;
  const racingStore = {
    getItem: (key) => {
      if (key === DRAFT_KEY && ++draftReads === 2) {
        const plans = JSON.parse(target.getItem(DRAFT_KEY));
        target.setItem(DRAFT_KEY, JSON.stringify(plans.map((plan) =>
          ({ ...plan, symbol: "000001" }))));
      }
      return target.getItem(key);
    },
    setItem: (key, value) => target.setItem(key, value),
  };
  assert.throws(() => restoreReviewBackup(racingStore, backup), /计划发生变化/);
  assert.equal(target.getItem(REVIEW_KEY), null);
  assert.equal(JSON.parse(target.getItem(DRAFT_KEY))[0].symbol, "000001");
});

test("review backup rejects calendar-invalid export times even with timezone", () => {
  const source = store();
  withReview(source);
  const backup = JSON.parse(serializeReviewBackup(source));
  const target = store();
  withPlan(target);
  for (const invalid of ["2026-02-30T08:00:00Z", "2026-10-21T08:00:00"]) {
    assert.throws(() => restoreReviewBackup(target,
      JSON.stringify({ ...backup, exported_at: invalid })), /备份版本/);
    assert.equal(target.getItem(REVIEW_KEY), null);
  }
  assert.throws(() => serializeReviewBackup(source,
    () => "2026-02-30T08:00:00Z"), /时间无效/);
});
