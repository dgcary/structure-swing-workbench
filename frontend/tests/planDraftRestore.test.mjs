import assert from "node:assert/strict";
import { test } from "node:test";
import { restoreDraftBackup, serializeDraftBackup } from "../src/planDraftBackup.ts";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";

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
