import assert from "node:assert/strict";
import { test } from "node:test";
import { restoreDraftBackup, serializeDraftBackup } from "../src/planDraftBackup.ts";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";
import { REVIEW_KEY, saveReview } from "../src/reviewStore.ts";

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
  saveReview(valid, { id: "plan-1", version: 1, symbol: "600000" },
    "观察", "结论", () => "review-1");
  const before = valid.getItem(REVIEW_KEY);
  assert.equal(restoreDraftBackup(valid, backup).length, 1);
  assert.equal(valid.getItem(REVIEW_KEY), before);

  const invalid = store();
  saveReview(invalid, { id: "plan-1", version: 1, symbol: "000001" },
    "观察", "结论", () => "review-1");
  assert.throws(() => restoreDraftBackup(invalid, backup), /不匹配/);
  assert.equal(invalid.getItem(DRAFT_KEY), null);
});
