import assert from "node:assert/strict";
import { test } from "node:test";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";
import { summarizeLocalDrafts } from "../src/localDraftSummary.ts";

function store() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
  };
}
const draft = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "manual" };

test("dashboard summary keeps only latest version per plan", () => {
  const storage = store();
  saveDraft(storage, draft, null, () => "p1", () => "2026-10-16T09:00:00Z");
  saveDraft(storage, { ...draft, notes: "new" }, "p1", () => "unused", () => "2026-10-17T09:00:00Z");
  saveDraft(storage, { ...draft, symbol: "000001" }, null, () => "p2", () => "2026-10-18T09:00:00Z");
  const result = summarizeLocalDrafts(storage);
  assert.equal(result.versionCount, 3);
  assert.deepEqual(result.latest.map((item) => [item.id, item.version]), [["p2", 1], ["p1", 2]]);
});

test("corrupt local storage is never reported as empty history", () => {
  const storage = store();
  assert.equal(summarizeLocalDrafts(storage).latest.length, 0);
  storage.setItem(DRAFT_KEY, "");
  assert.throws(() => summarizeLocalDrafts(storage));
});
