import assert from "node:assert/strict";
import { test } from "node:test";
import { DRAFT_KEY, readDrafts, saveDraft } from "../src/planDraftStore.ts";

function memoryStore() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); },
  };
}
const input = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "人工" };

test("new versions are appended to the latest browser history", () => {
  const store = memoryStore();
  const first = saveDraft(store, input, null, () => "plan-1");
  saveDraft(store, { ...input, notes: "修订" }, first.id);
  assert.deepEqual(readDrafts(store).map((item) => item.version), [2, 1]);
  assert.equal(readDrafts(store)[1].notes, "人工");
});

test("changing the stock of an existing plan fails without overwriting history", () => {
  const store = memoryStore();
  saveDraft(store, input, null, () => "plan-1");
  const before = store.getItem(DRAFT_KEY);
  assert.throws(() => saveDraft(store, { ...input, symbol: "000001" }, "plan-1"));
  assert.equal(store.getItem(DRAFT_KEY), before);
});

test("corrupt, duplicate or cross-symbol versions fail closed", () => {
  const store = memoryStore();
  const original = saveDraft(store, input, null, () => "plan-1").drafts[0];
  for (const records of [
    [original, original],
    [original, { ...original, version: 2, symbol: "000001" }],
    [{ ...original, entry: "NaN" }],
  ]) {
    store.setItem(DRAFT_KEY, JSON.stringify(records));
    const before = store.getItem(DRAFT_KEY);
    assert.throws(() => saveDraft(store, input, "plan-1"));
    assert.equal(store.getItem(DRAFT_KEY), before);
  }
});

test("invalid prices and missing editing ids never create a plan", () => {
  const store = memoryStore();
  assert.throws(() => saveDraft(store, input, "missing"));
  assert.throws(() => saveDraft(store, { ...input, entry: "0" }, null));
  assert.equal(store.getItem(DRAFT_KEY), null);
});

test("empty stored value is corruption, not permission to overwrite", () => {
  const store = memoryStore();
  store.setItem(DRAFT_KEY, "");
  assert.throws(() => saveDraft(store, input, null));
  assert.equal(store.getItem(DRAFT_KEY), "");
});

test("new plan ids work without secure-context crypto APIs", () => {
  const store = memoryStore();
  const saved = saveDraft(store, input, null);
  assert.equal(typeof saved.id, "string");
  assert.ok(saved.id.length > 0);
  assert.equal(readDrafts(store).length, 1);
});
