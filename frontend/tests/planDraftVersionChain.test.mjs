import assert from "node:assert/strict";
import { test } from "node:test";
import { DRAFT_KEY, readDrafts, saveDraft } from "../src/planDraftStore.ts";

test("rejects missing local plan versions", () => {
  const map = new Map();
  const storage = { getItem: (key) => map.get(key) ?? null, setItem: (key, value) => map.set(key, value) };
  const plan = { symbol: "600000", setup: "C", entry: "10", stop: "9", target: "12", notes: "" };
  saveDraft(storage, plan, null, () => "p1");
  saveDraft(storage, plan, "p1");
  const versions = readDrafts(storage);
  storage.setItem(DRAFT_KEY, JSON.stringify(versions.filter((item) => item.version !== 1)));
  assert.throws(() => readDrafts(storage), /版本链不完整/);
  assert.throws(() => saveDraft(storage, plan, "p1"), /版本链不完整/);
});
