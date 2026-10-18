import assert from "node:assert/strict";
import { test } from "node:test";
import { serializeDraftBackup } from "../src/planDraftBackup.ts";
import { DRAFT_KEY, saveDraft } from "../src/planDraftStore.ts";

const input = {
  symbol: "600000", setup: "C", entry: "10", stop: "9",
  target: "12", notes: "人工备注",
};
function memoryStore() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { data.set(key, value); },
  };
}

test("backup preserves validated versions and provenance without writing", () => {
  const store = memoryStore();
  const first = saveDraft(store, input, null, () => "manual-1", () => "2026-10-18T00:00:00.000Z");
  saveDraft(store, { ...input, notes: "修订" }, first.id,
    () => "unused", () => "2026-10-18T01:00:00.000Z");
  const before = store.getItem(DRAFT_KEY);
  const result = JSON.parse(serializeDraftBackup(store, () => "2026-10-18T02:00:00.000Z"));
  assert.equal(result.schema_version, "m8.manual_drafts.v1");
  assert.equal(result.exported_at, "2026-10-18T02:00:00.000Z");
  assert.deepEqual(result.records.map((row) => row.version), [2, 1]);
  assert.equal(result.records[1].notes, "人工备注");
  assert.equal(store.getItem(DRAFT_KEY), before);
});

test("corrupt local history refuses backup and does not modify source", () => {
  const store = memoryStore();
  store.setItem(DRAFT_KEY, "{not-json");
  const before = store.getItem(DRAFT_KEY);
  assert.throws(() => serializeDraftBackup(store));
  assert.equal(store.getItem(DRAFT_KEY), before);
});

test("unavailable browser storage or invalid timestamp never returns a backup", () => {
  assert.throws(() => serializeDraftBackup({
    getItem: () => { throw new Error("storage unavailable"); },
  }));
  assert.throws(() => serializeDraftBackup(memoryStore(), () => "invalid-time"),
    /备份时间无效/);
});
