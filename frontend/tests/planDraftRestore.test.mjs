import assert from "node:assert/strict";
import { test } from "node:test";
import { restoreDraftBackup, serializeDraftBackup } from "../src/planDraftBackup.ts";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";
import { REVIEW_KEY } from "../src/reviewStore.ts";

const input = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "人工" };
function store() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); } };
}
test("restore roundtrip and never overwrite existing plans", () => {
  const original = store();
  saveDraft(original, input, null, () => "plan-1");
  const backup = serializeDraftBackup(original);
  const target = store();
  assert.equal(restoreDraftBackup(target, backup).length, 1);
  assert.equal(target.getItem(DRAFT_KEY), original.getItem(DRAFT_KEY));
  assert.throws(() => restoreDraftBackup(target, backup));
});
test("invalid backup does not create plans", () => {
  const target = store();
  assert.throws(() => restoreDraftBackup(target, "{}"));
  assert.equal(target.getItem(DRAFT_KEY), null);
});

test("restore keeps linked local reviews but rejects mismatched symbols", () => {
  const source = store();
  saveDraft(source, input, null, () => "plan-1");
  const backup = serializeDraftBackup(source);
  const valid = store();
  // Legacy records can predate the draft restore; new writes reject orphans.
  const legacyReview = {
    id: "review-1", planId: "plan-1", version: 1, symbol: "600000",
    savedAt: "2026-10-19T07:00:00+08:00", observation: "观察", lesson: "结论",
  };
  valid.setItem(REVIEW_KEY, JSON.stringify([legacyReview]));
  const before = valid.getItem(REVIEW_KEY);
  assert.equal(restoreDraftBackup(valid, backup).length, 1);
  assert.equal(valid.getItem(REVIEW_KEY), before);

  const invalid = store();
  invalid.setItem(REVIEW_KEY, JSON.stringify([{ ...legacyReview, symbol: "000001" }]));
  assert.throws(() => restoreDraftBackup(invalid, backup), /不匹配/);
  assert.equal(invalid.getItem(DRAFT_KEY), null);
});
