import assert from "node:assert/strict";
import { test } from "node:test";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";
import { refreshLocalDrafts } from "../src/localDraftRefresh.ts";

const plan = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "" };

function memoryStore() {
  const data = new Map();
  return {
    getItem(key) { return data.get(key) ?? null; },
    setItem(key, value) { data.set(key, value); },
  };
}

test("refresh detects a newer version without changing unsaved editor fields", () => {
  const storage = memoryStore();
  saveDraft(storage, plan, null, () => "p1");
  assert.equal(refreshLocalDrafts(storage, "p1", 1).editingStale, false);
  saveDraft(storage, { ...plan, notes: "updated elsewhere" }, "p1", undefined, undefined, 1);
  const refreshed = refreshLocalDrafts(storage, "p1", 1);
  assert.equal(refreshed.editingStale, true);
  assert.equal(refreshed.summary.versionCount, 2);
  assert.deepEqual(refreshed.drafts.map((item) => item.version), [2, 1]);
  assert.equal(refreshed.drafts[0].notes, "updated elsewhere");
  assert.equal(refreshLocalDrafts(storage, "p1", 2).editingStale, false);
});

test("refresh reads one consistent snapshot even if storage changes during parsing", () => {
  const storage = memoryStore();
  saveDraft(storage, plan, null, () => "p1");
  const original = storage.getItem(DRAFT_KEY);
  saveDraft(storage, { ...plan, notes: "new" }, "p1", undefined, undefined, 1);
  const latest = storage.getItem(DRAFT_KEY);
  let reads = 0;
  const changingStore = {
    getItem(key) {
      reads++;
      return key === DRAFT_KEY ? (reads === 1 ? original : latest) : null;
    },
  };
  const refreshed = refreshLocalDrafts(changingStore, "p1", 1);
  assert.equal(reads, 1);
  assert.equal(refreshed.summary.versionCount, 1);
  assert.equal(refreshed.editingStale, false);
});

test("corrupted browser history is not silently presented as an empty plan list", () => {
  const storage = memoryStore();
  storage.setItem(DRAFT_KEY, "not-json");
  assert.throws(() => refreshLocalDrafts(storage, null, null));
});
