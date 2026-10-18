import assert from "node:assert/strict";
import { test } from "node:test";
import { DRAFT_KEY, readDrafts, saveDraft } from "../src/planDraftStore.ts";

const plan = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "" };

function memoryStore() {
  const map = new Map();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, value),
  };
}

test("stale tab cannot silently supersede a newer manual plan version", () => {
  const storage = memoryStore();
  saveDraft(storage, plan, null, () => "p1");
  saveDraft(storage, { ...plan, notes: "second tab" }, "p1", undefined, undefined, 1);
  const before = storage.getItem(DRAFT_KEY);
  assert.throws(
    () => saveDraft(storage, { ...plan, notes: "stale form" }, "p1", undefined, undefined, 1),
    /其他页面更新/,
  );
  assert.equal(storage.getItem(DRAFT_KEY), before);
  assert.deepEqual(readDrafts(storage).map((item) => item.version), [2, 1]);
  assert.equal(readDrafts(storage)[0].notes, "second tab");
});

test("refreshing the expected version allows a subsequent revision", () => {
  const storage = memoryStore();
  saveDraft(storage, plan, null, () => "p1");
  saveDraft(storage, plan, "p1", undefined, undefined, 1);
  saveDraft(storage, { ...plan, notes: "third" }, "p1", undefined, undefined, 2);
  assert.equal(readDrafts(storage)[0].version, 3);
  assert.equal(readDrafts(storage)[0].notes, "third");
});

test("invalid expected version is rejected without changing history", () => {
  const storage = memoryStore();
  saveDraft(storage, plan, null, () => "p1");
  const before = storage.getItem(DRAFT_KEY);
  for (const version of [0, -1, 1.5, Number.NaN]) {
    assert.throws(() => saveDraft(storage, plan, "p1", undefined, undefined, version));
    assert.equal(storage.getItem(DRAFT_KEY), before);
  }
});
